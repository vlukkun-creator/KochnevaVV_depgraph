"""Инструмент для построения графа зависимостей пакетов Python (pip)."""
import argparse
import os
import re
import sys
import json
import urllib.error
import urllib.request
import urllib.parse
from collections import deque

DEFAULT_REPO = "https://pypi.org/pypi"
DEFAULT_DEPTH = 3
MIN_DEPTH = 1
MAX_DEPTH = 50
NOT_SET = "<не задано>"
URL_SCHEMES = ("http", "https")
EXIT_OK = 0
EXIT_ERROR = 1
PACKAGE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CONFIG_KEYS = ("package", "repo", "test", "ascii", "depth", "filter", "reverse")
TIMEOUT_SECONDS = 10
HTTP_NOT_FOUND = 404
NAME_PATTERN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
EXTRA_PATTERN = re.compile(r"extra\s*==")
SEPARATOR_PATTERN = re.compile(r"[-_.]+")
TEST_NAME_PATTERN = re.compile(r"^[A-Z]+$")
COMMENT_SIGN = "#"


class ToolError(Exception):
    """Ошибка в работе программы: неверные параметры, нет файла и т.д."""


def build_parser():
    """Создает разборщик параметров командной строки."""
    parser = argparse.ArgumentParser(
        description="Граф зависимостей пакета Python (формат pip)"
    )
    parser.add_argument("--package", help="имя анализируемого пакета")
    parser.add_argument(
        "--repo",
        help="URL репозитория или путь к файлу тестового репозитория",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="тестовый режим: --repo это путь к файлу с описанием графа",
    )
    parser.add_argument(
        "--ascii", action="store_true",
        help="вывести зависимости в виде ASCII-дерева",
    )
    parser.add_argument(
        "--depth", default=str(DEFAULT_DEPTH),
        help=f"максимальная глубина анализа (по умолчанию {DEFAULT_DEPTH})",
    )
    parser.add_argument(
        "--filter",
        help="не учитывать пакеты, в имени которых есть эта подстрока",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="показать все параметры при запуске",
    )
    parser.add_argument(
        "--reverse", action="store_true",
        help="показать обратные зависимости (кто зависит от пакета)",
    )
    return parser


def check_package(name):
    """Проверяет имя пакета: оно не пустое и без лишних символов."""
    if not name:
        raise ToolError("не указано имя пакета (параметр --package)")
    if not PACKAGE_PATTERN.match(name):
        raise ToolError(f"неверное имя пакета: {name}")
    return name


def check_depth(text):
    """Переводит глубину в число и проверяет, что она в нужных границах."""
    try:
        depth = int(text)
    except ValueError:
        raise ToolError(f"глубина должна быть целым числом: {text}")
    if not MIN_DEPTH <= depth <= MAX_DEPTH:
        raise ToolError(
            f"глубина должна быть от {MIN_DEPTH} до {MAX_DEPTH}: {depth}"
        )
    return depth


def check_url(repo):
    """Проверяет, что строка похожа на адрес сайта (http или https)."""
    parts = urllib.parse.urlparse(repo)
    if parts.scheme not in URL_SCHEMES or not parts.netloc:
        raise ToolError(
            f"неверный URL репозитория: {repo} "
            "(если это путь к файлу, добавьте параметр --test)"
        )
    return repo.rstrip("/")


def check_test_file(path):
    """Проверяет, что по этому пути есть файл тестового репозитория."""
    if not path:
        raise ToolError("в тестовом режиме нужно указать файл (--repo)")
    if not os.path.exists(path):
        raise ToolError(f"файл тестового репозитория не найден: {path}")
    if not os.path.isfile(path):
        raise ToolError(f"это не файл, а папка: {path}")
    return path


def check_repo(repo, test_mode):
    """Проверяет параметр --repo: файл в тестовом режиме, иначе URL."""
    if test_mode:
        return check_test_file(repo)
    if repo is None:
        return DEFAULT_REPO
    return check_url(repo)


def check_filter(text, package):
    """Проверяет подстроку для фильтра: она не пустая и не убирает пакет."""
    if text is None:
        return None
    if not text:
        raise ToolError("подстрока для фильтра не должна быть пустой")
    if text in package:
        raise ToolError(
            f"имя пакета {package} содержит подстроку фильтра {text}"
        )
    return text


def read_config(args):
    """Проверяет все параметры и собирает их в один словарь."""
    package = check_package(args.package)
    return {
        "package": package,
        "repo": check_repo(args.repo, args.test),
        "test": args.test,
        "ascii": args.ascii,
        "depth": check_depth(args.depth),
        "filter": check_filter(args.filter, package),
        "reverse": args.reverse,
    }


def show_config(config):
    """Печатает все параметры в виде ключ = значение."""
    print("Параметры запуска:")
    for key in CONFIG_KEYS:
        value = config[key]
        if value is None:
            value = NOT_SET
        print(f"  {key} = {value}")


def normalize_name(name):
    """Делает имя пакета маленькими буквами, а ._- заменяет на дефис."""
    return SEPARATOR_PATTERN.sub("-", name).lower()


def fetch_json(url):
    """Скачивает страницу по адресу и превращает ответ в словарь."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as answer:
            raw = answer.read()
    except urllib.error.HTTPError as error:
        if error.code == HTTP_NOT_FOUND:
            raise ToolError(f"пакет не найден в репозитории: {url}")
        raise ToolError(
            f"репозиторий вернул ошибку {error.code}: {url}"
        )
    except OSError as error:
        raise ToolError(f"не удалось подключиться к {url}")
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as error:
        raise ToolError(f"репозиторий вернул неверные данные: {url}")


def read_requirements(data):
    """Достает из ответа репозитория список строк с зависимостями."""
    try:
        lines = data["info"]["requires_dist"]
    except (KeyError, TypeError):
        raise ToolError("в ответе репозитория нет данных о пакете")
    return lines or []


def parse_requirement(line):
    """Берет из строки зависимости имя пакета.

    Если зависимость нужна только для дополнительной опции (extra),
    возвращает None, потому что pip ее по умолчанию не ставит.
    """
    if EXTRA_PATTERN.search(line):
        return None
    match = NAME_PATTERN.match(line)
    if match is None:
        return None
    return normalize_name(match.group(1))


def get_direct_dependencies(repo, package):
    """Возвращает прямые зависимости пакета из репозитория без повторов."""
    data = fetch_json(f"{repo}/{package}/json")
    names = []
    for line in read_requirements(data):
        name = parse_requirement(line)
        if name is not None and name not in names:
            names.append(name)
    return names


def parse_test_line(number, line):
    """Разбирает строку тестового файла вида  A: B C.

    Пустые строки и комментарии пропускает (возвращает None).
    """
    text = line.split(COMMENT_SIGN, 1)[0].strip()
    if not text:
        return None
    name, separator, rest = text.partition(":")
    if not separator:
        raise ToolError(f"строка {number}: нет двоеточия после имени")
    name = name.strip()
    deps = []
    for item in rest.split():
        if item not in deps:
            deps.append(item)
    for item in [name] + deps:
        if not TEST_NAME_PATTERN.match(item):
            raise ToolError(
                f"строка {number}: неверное имя пакета '{item}' "
                "(нужны большие латинские буквы)"
            )
    return name, deps


def read_test_repo(path):
    """Читает файл тестового репозитория в словарь пакет -> зависимости."""
    try:
        with open(path, encoding="utf-8-sig") as file:
            lines = file.read().splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ToolError(f"не удалось прочитать файл {path}")
    repo = {}
    for number, line in enumerate(lines, start=1):
        item = parse_test_line(number, line)
        if item is None:
            continue
        name, deps = item
        if name in repo:
            raise ToolError(f"строка {number}: пакет {name} описан второй раз")
        repo[name] = deps
    return repo


def check_known(repo, package):
    """Проверяет, что пакет упоминается в тестовом репозитории."""
    known = set(repo)
    for deps in repo.values():
        known.update(deps)
    if package not in known:
        raise ToolError(f"пакет {package} не найден в тестовом репозитории")


def get_root(config):
    """Возвращает имя пакета, с которого начинается анализ."""
    if config["test"]:
        return config["package"]
    return normalize_name(config["package"])


def test_deps(repo, name):
    """Берет зависимости пакета из словаря тестового репозитория."""
    return repo.get(name, [])


def is_filtered(name, substring):
    """Проверяет, что пакет надо пропустить из-за подстроки фильтра."""
    return substring is not None and substring in name


def build_graph(root, load_deps, source, max_depth, substring):
    """Строит граф зависимостей обходом в ширину (BFS), без рекурсии.

    Граф это словарь: имя пакета -> список его зависимостей.
    Зависимости берет функция load_deps(source, имя): source это словарь
    тестового репозитория или адрес настоящего.
    Пакеты на предельной глубине попадают в граф, но не раскрываются.
    Если пакет уже встречался (цикл), второй раз его не обходим,
    но ребро к нему сохраняем.
    """
    graph = {}
    seen = {root}
    queue = deque([(root, 0)])
    while queue:
        name, level = queue.popleft()
        if level >= max_depth:
            graph[name] = []
            continue
        found = load_deps(source, name)
        deps = [d for d in found if not is_filtered(d, substring)]
        graph[name] = deps
        for dep in deps:
            if dep not in seen:
                seen.add(dep)
                queue.append((dep, level + 1))
    return graph


def forward_graph(config):
    """Строит граф зависимостей пакета, который выбрал пользователь."""
    root = get_root(config)
    if config["test"]:
        repo = read_test_repo(config["repo"])
        check_known(repo, root)
        loader, source = test_deps, repo
    else:
        loader, source = get_direct_dependencies, config["repo"]
    depth, substring = config["depth"], config["filter"]
    return build_graph(root, loader, source, depth, substring)


def graph_lines(graph):
    """Делает строки для вывода: на каждой пакет и его зависимости."""
    lines = []
    for name, deps in graph.items():
        text = " ".join(deps) if deps else "-"
        lines.append(f"{name} -> {text}")
    return lines


def show_graph(config):
    """Строит граф и печатает его на экран (этапы 3 и 4)."""
    graph = forward_graph(config)
    print(f"Граф зависимостей пакета {get_root(config)}:")
    print(f"(глубина анализа: {config['depth']})")
    for line in graph_lines(graph):
        print(f"  {line}")
    print(f"Всего пакетов в графе: {len(graph)}")


def reverse_edges(repo):
    """Переворачивает граф: пакет -> список тех, кто от него зависит."""
    reverse = {}
    for name, deps in repo.items():
        for dep in deps:
            reverse.setdefault(dep, []).append(name)
    return reverse


def reverse_graph(config):
    """Строит граф обратных зависимостей тем же обходом BFS.

    Работает только в тестовом режиме, потому что в реальном репозитории
    нельзя узнать, какие пакеты зависят от данного.
    """
    if not config["test"]:
        raise ToolError(
            "обратные зависимости работают только в тестовом режиме "
            "(параметр --test): реальный репозиторий не говорит, "
            "кто зависит от пакета"
        )
    package = config["package"]
    repo = read_test_repo(config["repo"])
    check_known(repo, package)
    source = reverse_edges(repo)
    depth, substring = config["depth"], config["filter"]
    return build_graph(package, test_deps, source, depth, substring)


def reverse_lines(graph):
    """Делает строки вида  D <- B C  только для пакетов, у которых они есть."""
    return [
        f"{name} <- {' '.join(users)}" for name, users in graph.items() if users
    ]


def count_users(graph):
    """Считает разные пакеты, которые встретились как зависящие."""
    users = set()
    for names in graph.values():
        users.update(names)
    return len(users)


def show_reverse(config):
    """Печатает пакеты, которые зависят от выбранного пакета (этап 4)."""
    graph = reverse_graph(config)
    package = config["package"]
    print(f"Обратные зависимости пакета {package} (кто от него зависит):")
    lines = reverse_lines(graph)
    for line in lines:
        print(f"  {line}")
    if not lines:
        print("  (от этого пакета никто не зависит)")
    print(f"Всего пакетов, которые зависят от {package}: {count_users(graph)}")


def run(config, debug):
    """Выполняет главное действие программы в зависимости от параметров."""
    if debug:
        show_config(config)
    if config["reverse"]:
        show_reverse(config)
        return
    show_graph(config)


def main(argv=None):
    """Запускает программу, возвращает код завершения."""
    args = build_parser().parse_args(argv)
    try:
        config = read_config(args)
        run(config, args.debug)
    except ToolError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
