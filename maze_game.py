#!/usr/bin/env python3
"""
LABYRINTH OF SHADOWS — Текстовый roguelike в генерируемом лабиринте.
Управление: WASD/стрелки — движение, P — инвентарь, Q — выход.

Иконки:
  @ — игрок          # — стена
  > — выход          $ — сокровище
  ! — зелье здоровья  * — ключ
  & — монстр         ~ — ловушка
  . — пустой пол     : — пройденная клетка
"""

import random
import math
import os
import sys
import time

try:
    import msvcrt
    IS_WINDOWS = True
except ImportError:
    IS_WINDOWS = False
    import tty, termios

# ── Настройки ──────────────────────────────────────────────────────────
WIDTH, HEIGHT = 61, 31          # нечётные размеры для стен-клеток
VIEW_RADIUS = 5                 # радиус видимости (туман войны)
BASE_MONSTERS = 4
BASE_TREASURES = 5
BASE_TRAPS = 3
BASE_POTIONS = 2
BASE_KEY_CHANCE = 0.3

TILE_WALL  = '#'
TILE_FLOOR = '.'
TILE_VISITED = ':'
TILE_EXIT  = '>'
TILE_PLAYER = '@'
TILE_MONSTER = '&'
TILE_TREASURE = '$'
TILE_POTION = '!'
TILE_TRAP = '~'
TILE_KEY = '*'

# ── Цвета (ANSI) ──────────────────────────────────────────────────────
C_RESET   = '\033[0m'
C_BOLD    = '\033[1m'
C_DIM     = '\033[2m'
C_RED     = '\033[91m'
C_GREEN   = '\033[92m'
C_YELLOW  = '\033[93m'
C_BLUE    = '\033[94m'
C_MAGENTA = '\033[95m'
C_CYAN    = '\033[96m'
C_WHITE   = '\033[97m'
C_BG_RED  = '\033[41m'
C_GRAY    = '\033[90m'

TILE_COLORS = {
    TILE_WALL:     C_DIM + C_WHITE,
    TILE_FLOOR:    C_WHITE,
    TILE_VISITED:  C_GRAY,
    TILE_EXIT:     C_GREEN + C_BOLD,
    TILE_PLAYER:   C_CYAN + C_BOLD,
    TILE_MONSTER:  C_RED + C_BOLD,
    TILE_TREASURE: C_YELLOW + C_BOLD,
    TILE_POTION:   C_GREEN,
    TILE_TRAP:     C_MAGENTA,
    TILE_KEY:      C_YELLOW + C_BOLD,
}


# ══════════════════════════════════════════════════════════════════════
#  ГЕНЕРАТОР ЛАБИРИНТА (рекурсивное деление + коридоры)
# ══════════════════════════════════════════════════════════════════════

def generate_maze(w, h):
    """Создаёт лабиринт размером w×h (оба нечётные). Возвращает 2D-список."""
    grid = [[TILE_WALL] * h for _ in range(w)]

    def carve(x, y):
        grid[x][y] = TILE_FLOOR
        dirs = [(0, 2), (0, -2), (2, 0), (-2, 0)]
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = x + dx, y + dy
            if 0 < nx < w and 0 < ny < h and grid[nx][ny] == TILE_WALL:
                grid[x + dx // 2][y + dy // 2] = TILE_FLOOR
                carve(nx, ny)

    # Начинаем с (1,1) — гарантированно нечётные координаты
    carve(1, 1)

    # Добавляем случайные проходы для цикличности (10% стен между проходами)
    for x in range(2, w - 1, 1):
        for y in range(2, h - 1, 1):
            if grid[x][y] == TILE_WALL and random.random() < 0.08:
                neighbours = 0
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    if grid[x + dx][y + dy] == TILE_FLOOR:
                        neighbours += 1
                if neighbours >= 2:
                    grid[x][y] = TILE_FLOOR

    return grid


def get_floor_cells(grid, w, h):
    cells = []
    for x in range(w):
        for y in range(h):
            if grid[x][y] == TILE_FLOOR:
                cells.append((x, y))
    return cells


# ══════════════════════════════════════════════════════════════════════
#  МОНСТРЫ (простой ИИ — преследование игрока по BFS)
# ══════════════════════════════════════════════════════════════════════

class Monster:
    def __init__(self, x, y, hp, damage, xp, name):
        self.x, self.y = x, y
        self.hp = hp
        self.max_hp = hp
        self.damage = damage
        self.xp = xp
        self.name = name
        self.stunned = 0

    def take_damage(self, dmg):
        self.hp -= dmg
        return self.hp <= 0

    def move_towards(self, px, py, grid, w, h, others):
        if self.stunned > 0:
            self.stunned -= 1
            return
        dist = abs(self.x - px) + abs(self.y - py)
        if dist > 20:
            return  # далеко — не преследует

        best = None
        best_dist = dist
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = self.x + dx, self.y + dy
            if 0 <= nx < w and 0 <= ny < h and grid[nx][ny] != TILE_WALL:
                occupied = (nx == px and ny == py) or any(
                    o.x == nx and o.y == ny for o in others if o is not self
                )
                if not occupied:
                    d = abs(nx - px) + abs(ny - py)
                    if d < best_dist:
                        best_dist = d
                        best = (nx, ny)
        if best:
            self.x, self.y = best


MONSTER_TYPES = [
    ("Паук",       3, 1, 5),
    ("Скелет",     5, 2, 10),
    ("Тень",       4, 1, 8),
    ("Демон",      8, 3, 20),
    ("Дракон",    15, 5, 50),
]


# ══════════════════════════════════════════════════════════════════════
#  ИГРОК
# ══════════════════════════════════════════════════════════════════════

class Player:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.hp = 20
        self.max_hp = 20
        self.attack = 3
        self.defense = 0
        self.xp = 0
        self.level = 1
        self.gold = 0
        self.keys = 0
        self.potions = 3
        self.visited = set()
        self.inventory = []

    @property
    def xp_to_next(self):
        return self.level * 15 + 10

    def level_up_check(self):
        ups = 0
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.level += 1
            self.max_hp += 5
            self.hp = min(self.hp + 5, self.max_hp)
            self.attack += 1
            self.defense += 1
            ups += 1
        return ups

    def use_potion(self):
        if self.potions > 0:
            heal = min(8 + self.level * 2, self.max_hp - self.hp)
            self.hp += heal
            self.potions -= 1
            return heal
        return 0


# ══════════════════════════════════════════════════════════════════════
#  УРОВЕНЬ / МИР
# ══════════════════════════════════════════════════════════════════════

class Level:
    def __init__(self, depth):
        self.depth = depth
        w = min(WIDTH + depth * 4, 99)
        h = min(HEIGHT + depth * 2, 51)
        # Ensure odd
        w = w if w % 2 == 1 else w + 1
        h = h if h % 2 == 1 else h + 1
        self.w, self.h = w, h
        self.grid = generate_maze(w, h)
        self.floor_cells = get_floor_cells(self.grid, w, h)
        random.shuffle(self.floor_cells)

        self.entities = []     # монстры
        self.items = {}        # (x,y) -> item_type
        self.exit_pos = None
        self.exit_locked = random.random() < 0.4 and depth > 1
        self.messages = []

    def populate(self, player_level):
        cells = list(self.floor_cells)
        random.shuffle(cells)
        idx = 0

        # Стартовая позиция игрока — (1,1)
        spawn = (1, 1)
        if spawn in cells:
            cells.remove(spawn)

        # Выход — максимально далеко от старта
        def dist_from_spawn(c):
            return abs(c[0] - 1) + abs(c[1] - 1)
        cells.sort(key=dist_from_spawn, reverse=True)
        self.exit_pos = cells.pop(0)
        idx = len(cells)

        # Монстры
        n_monsters = BASE_MONSTERS + self.depth * 2
        available_types = [m for m in MONSTER_TYPES if m[2] + m[1] <= 3 + player_level * 2]
        if not available_types:
            available_types = MONSTER_TYPES[:1]

        for _ in range(min(n_monsters, len(cells))):
            c = cells.pop()
            if random.random() < 0.3 and len(available_types) > 1:
                mt = random.choice(available_types[1:])
            else:
                mt = available_types[0]
            hp_bonus = int(mt[1] * 0.3 * self.depth)
            dmg_bonus = self.depth // 3
            m = Monster(c[0], c[1], mt[1] + hp_bonus, mt[2] + dmg_bonus, mt[3], mt[0])
            self.entities.append(m)

        # Сокровища
        n_treasures = BASE_TREASURES + self.depth
        for _ in range(min(n_treasures, len(cells))):
            c = cells.pop()
            gold = random.randint(5 + self.depth * 3, 15 + self.depth * 5)
            self.items[c] = ('treasure', gold)

        # Зелья
        for _ in range(BASE_POTIONS + self.depth // 2):
            if cells:
                c = cells.pop()
                self.items[c] = ('potion', 0)

        # Ловушки
        for _ in range(BASE_TRAPS + self.depth):
            if cells:
                c = cells.pop()
                self.items[c] = ('trap', random.randint(2, 4 + self.depth * 2))

        # Ключи (если выход заперт)
        if self.exit_locked:
            n_keys = 1
            for _ in range(n_keys):
                if cells:
                    c = cells.pop()
                    self.items[c] = ('key', 0)


# ══════════════════════════════════════════════════════════════════════
#  ОТРИСОВКА
# ══════════════════════════════════════════════════════════════════════

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def distance(x1, y1, x2, y2):
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def render(player, level, log_messages):
    clear()
    w, h = level.w, level.h
    px, py = player.x, player.y

    # Определяем видимые клетки (туман войны)
    visible = set()
    for x in range(max(0, px - VIEW_RADIUS), min(w, px + VIEW_RADIUS + 1)):
        for y in range(max(0, py - VIEW_RADIUS), min(h, py + VIEW_RADIUS + 1)):
            if distance(px, py, x, y) <= VIEW_RADIUS:
                visible.add((x, y))

    # Собираем карту для отрисовки
    canvas = {}
    for x in range(w):
        for y in range(h):
            if (x, y) in visible:
                canvas[(x, y)] = level.grid[x][y]
                player.visited.add((x, y))
            elif (x, y) in player.visited:
                canvas[(x, y)] = TILE_VISITED

    # Предметы на видимых клетках
    for (ix, iy), item in level.items.items():
        if (ix, iy) in visible:
            if item[0] == 'treasure':
                canvas[(ix, iy)] = TILE_TREASURE
            elif item[0] == 'potion':
                canvas[(ix, iy)] = TILE_POTION
            elif item[0] == 'trap':
                canvas[(ix, iy)] = TILE_TRAP
            elif item[0] == 'key':
                canvas[(ix, iy)] = TILE_KEY

    # Монстры на видимых клетках
    for m in level.entities:
        if (m.x, m.y) in visible:
            canvas[(m.x, m.y)] = TILE_MONSTER

    # Выход
    if level.exit_pos in visible:
        ex, ey = level.exit_pos
        canvas[(ex, ey)] = TILE_EXIT

    # Игрок
    canvas[(px, py)] = TILE_PLAYER

    # ── HUD (верхняя строка) ─────────────────────────────────────────
    hp_bar_len = 20
    hp_filled = int(player.hp / player.max_hp * hp_bar_len)
    hp_bar = ('█' * hp_filled + '░' * (hp_bar_len - hp_filled))

    if player.hp / player.max_hp > 0.6:
        hp_color = C_GREEN
    elif player.hp / player.max_hp > 0.3:
        hp_color = C_YELLOW
    else:
        hp_color = C_RED

    xp_filled = int(player.xp / player.xp_to_next * 10) if player.xp_to_next > 0 else 0
    xp_bar = '▓' * xp_filled + '░' * (10 - xp_filled)

    title = f"{C_BOLD}{C_CYAN}◆ ЛАБИРИНТ ТЕНЕЙ ◆{C_RESET}"
    stats = (
        f"  {C_RED}HP [{hp_color}{hp_bar}{C_RESET}{C_RED}]{player.hp}/{player.max_hp}{C_RESET}"
        f"  {C_BLUE}Ур.{player.level}{C_RESET}"
        f"  {C_YELLOW}XP [{C_BLUE}{xp_bar}{C_YELLOW}] {player.xp}/{player.xp_to_next}{C_RESET}"
        f"  {C_YELLOW}ЗОЛОТО:{player.gold}{C_RESET}"
        f"  {C_GREEN}ЗЕЛЬЯ:{player.potions}{C_RESET}"
        f"  {C_MAGENTA}КЛЮЧИ:{player.keys}{C_RESET}"
    )
    floor_info = f"  {C_DIM}Этаж {level.depth}{C_RESET}"
    lock_info = f"  {C_RED}🔒 ЗАПЕРТ{C_RESET}" if level.exit_locked else ""

    # ── Карта ─────────────────────────────────────────────────────────
    screen_lines = []
    screen_lines.append(f" {title}{stats}{floor_info}{lock_info}")
    screen_lines.append(f" {C_DIM}{'─' * (w + 2)}{C_RESET}")

    for y in range(h):
        row = ""
        for x in range(w):
            ch = canvas.get((x, y), ' ')
            if (x, y) in visible:
                color = TILE_COLORS.get(ch, C_WHITE)
                row += f"{color}{ch}{C_RESET}"
            elif (x, y) in player.visited:
                row += f"{C_DIM}{C_GRAY}{ch}{C_RESET}"
            else:
                row += ' '
        screen_lines.append(f" {C_DIM}│{C_RESET}{row}{C_DIM}│{C_RESET}")

    screen_lines.append(f" {C_DIM}{'─' * (w + 2)}{C_RESET}")

    # ── Сообщения ─────────────────────────────────────────────────────
    for msg in log_messages[-4:]:
        screen_lines.append(f" {msg}")
    # Пустые строки чтобы высота экрана была стабильна
    for _ in range(4 - min(len(log_messages), 4)):
        screen_lines.append("")

    # ── Подсказки ─────────────────────────────────────────────────────
    screen_lines.append(
        f" {C_DIM}WASD/стрелки: ход | "
        f"H: зелье | "
        f"Q: выход{C_RESET}"
    )

    print('\n'.join(screen_lines))


# ══════════════════════════════════════════════════════════════════════
#  ВВОД
# ══════════════════════════════════════════════════════════════════════

def get_key():
    if IS_WINDOWS:
        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):
            ch2 = msvcrt.getch()
            mapping = {
                b'H': 'up', b'P': 'down',
                b'K': 'left', b'R': 'right',
            }
            return mapping.get(ch2, None)
        return ch.decode('utf-8', errors='ignore').lower()
    else:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                ch2 = sys.stdin.read(1)
                ch3 = sys.stdin.read(1)
                mapping = {'A': 'up', 'B': 'down', 'C': 'right', 'D': 'left'}
                return mapping.get(ch3, None)
            return ch.lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ══════════════════════════════════════════════════════════════════════
#  БОЕВАЯ СИСТЕМА
# ══════════════════════════════════════════════════════════════════════

def combat(player, monster, messages):
    """Простой автоматический бой."""
    messages.append(f"{C_RED}⚔ Бой с {monster.name}! (HP:{monster.hp}/{monster.max_hp}){C_RESET}")

    turn = 0
    while player.hp > 0 and monster.hp > 0:
        turn += 1
        # Игрок атакует
        dmg = max(1, player.attack + random.randint(-1, 2) - monster.damage // 2)
        killed = monster.take_damage(dmg)
        messages.append(
            f"  {C_CYAN}Вы{C_RESET} наносите {dmg} урона. "
            f"{C_RED}{monster.name}: {monster.hp}/{monster.max_hp} HP{C_RESET}"
        )
        if killed:
            messages.append(
                f"  {C_GREEN}✓ {monster.name} повержен! +{monster.xp} XP{C_RESET}"
            )
            player.xp += monster.xp
            return True

        # Монстр атакует
        mdmg = max(1, monster.damage + random.randint(-1, 1) - player.defense // 2)
        player.hp -= mdmg
        messages.append(
            f"  {C_RED}{monster.name}{C_RESET} наносит {mdmg} урона. "
            f"{C_CYAN}Вы: {player.hp}/{player.max_hp} HP{C_RESET}"
        )

        if turn > 20:
            messages.append(f"{C_YELLOW}Бой затянулся — монстр сбежал!{C_RESET}")
            return False

    return player.hp > 0


# ══════════════════════════════════════════════════════════════════════
#  ГЛАВНЫЙ ИГРОВОЙ ЦИКЛ
# ══════════════════════════════════════════════════════════════════════

def game_loop():
    # Начальный экран
    clear()
    print(f"""
{C_BOLD}{C_CYAN}
    ╔══════════════════════════════════════╗
    ║     ◆ ЛАБИРИНТ ТЕНЕЙ ◆              ║
    ║                                      ║
    ║  Тёмные коридоры ждут тебя...        ║
    ║  На каждом этаже — новые опасности   ║
    ║  и сокровища.                        ║
    ║                                      ║
    ║  Найди выход, собирай золото         ║
    ║  и сражайся с чудовищами!            ║
    ║                                      ║
    ║  {C_WHITE}WASD / стрелки — движение{C_CYAN}          ║
    ║  {C_WHITE}H — выпить зелье{C_CYAN}                   ║
    ║  {C_WHITE}Q — выход{C_CYAN}                         ║
    ╚══════════════════════════════════════╝
{C_RESET}""")
    print(f"    {C_DIM}Нажмите любую клавишу для начала...{C_RESET}")
    get_key()

    player = Player(1, 1)
    depth = 0
    monsters_killed = 0

    while True:
        depth += 1
        level = Level(depth)
        level.populate(player.level)

        # Сообщения
        log = []
        log.append(f"{C_CYAN}═══ Этаж {depth} ═══{C_RESET}")
        if level.exit_locked:
            log.append(f"{C_RED}Выход заперт! Найдите ключ!{C_RESET}")
        log.append(f"{C_DIM}Враги: {len(level.entities)} | "
                    f"Сокровищ: {sum(1 for v in level.items.values() if v[0] == 'treasure')}{C_RESET}")

        # Помещаем игрока
        player.x, player.y = 1, 1

        while True:
            # Проверяем смерть
            if player.hp <= 0:
                clear()
                print(f"""
{C_BOLD}{C_RED}
    ╔══════════════════════════════════════╗
    ║        ВЫ ПОГИБЛИ!                  ║
    ║                                      ║
    ║  Этаж: {depth:>3}                          ║
    ║  Золото: {player.gold:<5}                     ║
    ║  Уровень: {player.level:<3}                        ║
    ║  Врагов повержено: {monsters_killed:<3}            ║
    ╚══════════════════════════════════════╝
{C_RESET}""")
                return

            # Обновляем позиции монстров
            alive_monsters = []
            for m in level.entities:
                m.move_towards(player.x, player.y, level.grid, level.w, level.h,
                               alive_monsters + [player])
                alive_monsters.append(m)
            level.entities = alive_monsters

            # Проверяем столкновения с монстрамами
            for m in list(level.entities):
                if m.x == player.x and m.y == player.y:
                    result = combat(player, m, log)
                    if result:
                        level.entities.remove(m)
                        monsters_killed += 1

            # Проверяем, что игрок жив после боя
            if player.hp <= 0:
                continue

            # Проверяем ловушки (автоматический урон при наступании)
            if (player.x, player.y) in level.items:
                item = level.items[(player.x, player.y)]
                if item[0] == 'trap':
                    trap_dmg = item[1]
                    player.hp -= trap_dmg
                    log.append(f"{C_MAGENTA}~ Ловушка! -{trap_dmg} HP{C_RESET}")
                    del level.items[(player.x, player.y)]

            render(player, level, log)

            # Ввод
            key = get_key()
            if key is None:
                continue

            dx, dy = 0, 0
            if key == 'w' or key == 'up':    dy = -1
            elif key == 's' or key == 'down':  dy = 1
            elif key == 'a' or key == 'left':  dx = -1
            elif key == 'd' or key == 'right': dx = 1
            elif key == 'h':
                healed = player.use_potion()
                if healed > 0:
                    log.append(f"{C_GREEN}♥ Выпито зелье! +{healed} HP ({player.potions} осталось){C_RESET}")
                else:
                    log.append(f"{C_DIM}Зелий нет!{C_RESET}")
                continue
            elif key == 'q':
                print(f"\n{C_DIM}До свидания!{C_RESET}")
                return
            elif key == 'i':
                continue
            else:
                continue

            # Движение
            nx, ny = player.x + dx, player.y + dy
            if 0 <= nx < level.w and 0 <= ny < level.h:
                if level.grid[nx][ny] != TILE_WALL:
                    player.x, player.y = nx, ny

            # Проверяем предметы на клетке
            if (player.x, player.y) in level.items:
                item = level.items[(player.x, player.y)]
                if item[0] == 'treasure':
                    gold = item[1]
                    player.gold += gold
                    log.append(f"{C_YELLOW}💰 +{gold} золота{C_RESET}")
                    del level.items[(player.x, player.y)]
                elif item[0] == 'potion':
                    player.potions += 1
                    log.append(f"{C_GREEN}🧪 Зелье подобрано! ({player.potions} шт.){C_RESET}")
                    del level.items[(player.x, player.y)]
                elif item[0] == 'key':
                    player.keys += 1
                    log.append(f"{C_YELLOW}🔑 Ключ найден!{C_RESET}")
                    del level.items[(player.x, player.y)]

            # Проверяем выход
            if (player.x, player.y) == level.exit_pos:
                if level.exit_locked and player.keys <= 0:
                    log.append(f"{C_RED}🔒 Выход заперт! Найдите ключ!{C_RESET}")
                else:
                    if level.exit_locked:
                        player.keys -= 1
                    # Бонус за этаж
                    bonus_gold = 10 + depth * 5
                    player.gold += bonus_gold
                    level_ups = player.level_up_check()
                    log_msg = f"{C_GREEN}▶ Выход найден! +{bonus_gold} золота{C_RESET}"
                    if level_ups:
                        log_msg += f" {C_CYAN}★ LEVEL UP! Ур.{player.level}{C_RESET}"
                    log.append(log_msg)
                    break

            # Level up check
            level_ups = player.level_up_check()
            if level_ups:
                log.append(f"{C_CYAN}★ LEVEL UP! Ур.{player.level} (+5 HP, +1 ATK, +1 DEF){C_RESET}")

            # Ограничиваем историю
            if len(log) > 50:
                log = log[-50:]


def main():
    try:
        game_loop()
    except KeyboardInterrupt:
        print(f"\n{C_DIM}До свидания!{C_RESET}")
        sys.exit(0)


if __name__ == '__main__':
    main()
