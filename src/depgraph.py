"""Инструмент для построения графа зависимостей пакетов Python (pip)."""
import argparse
import os
import re
import sys
import urllib.parse

DEFAULT_REPO = "https://pypi.org/pypi"
DEFAULT_DEPTH = 3
MIN_DEPTH = 1
MAX_DEPTH = 50
NOT_SET = "<не задано>"
URL_SCHEMES = ("http", "https")
EXIT_OK = 0
EXIT_ERROR = 1
PACKAGE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CONFIG_KEYS = ("package", "repo", "test", "ascii", "depth", "filter")


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
    }


def show_config(config):
    """Печатает все параметры в виде ключ = значение."""
    print("Параметры запуска:")
    for key in CONFIG_KEYS:
        value = config[key]
        if value is None:
            value = NOT_SET
        print(f"  {key} = {value}")


def main(argv=None):
    """Запускает программу, возвращает код завершения."""
    args = build_parser().parse_args(argv)
    try:
        config = read_config(args)
        show_config(config)
    except ToolError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
