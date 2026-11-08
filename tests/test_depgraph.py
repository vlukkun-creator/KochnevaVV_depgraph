"""Тесты для инструмента depgraph."""
import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout

import depgraph
from depgraph import ToolError

HERE = os.path.dirname(os.path.abspath(__file__))
REPOS = os.path.join(HERE, "repos")
EXPECTED_DEFAULT_DEPTH = 3
EXPECTED_BAD_CODE = 1
EXPECTED_ARGPARSE_CODE = 2


def repo_path(name):
    """Возвращает путь к тестовому файлу репозитория."""
    return os.path.join(REPOS, name)


def run_main(argv):
    """Запускает main и возвращает код, вывод и текст ошибок."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = depgraph.main(argv)
    return code, out.getvalue(), err.getvalue()


class ConfigTest(unittest.TestCase):
    """Проверка параметров командной строки."""

    def parse(self, argv):
        """Разбирает параметры и проверяет их."""
        args = depgraph.build_parser().parse_args(argv)
        return depgraph.read_config(args)

    def test_defaults(self):
        """Без лишних параметров берутся значения по умолчанию."""
        config = self.parse(["--package", "requests"])
        self.assertEqual(config["repo"], depgraph.DEFAULT_REPO)
        self.assertEqual(config["depth"], EXPECTED_DEFAULT_DEPTH)
        self.assertIsNone(config["filter"])

    def test_no_package(self):
        """Без имени пакета будет ошибка."""
        with self.assertRaises(ToolError):
            self.parse([])

    def test_bad_package(self):
        """Имя пакета с лишними символами не подходит."""
        with self.assertRaises(ToolError):
            self.parse(["--package", "a b!"])

    def test_bad_depth(self):
        """Глубина должна быть числом в границах."""
        for text in ("x", "0", "-1", "51", "1.5"):
            with self.assertRaises(ToolError):
                self.parse(["--package", "a", "--depth", text])

    def test_bad_url(self):
        """Неверный URL дает ошибку, а слэш в конце убирается."""
        with self.assertRaises(ToolError):
            self.parse(["--package", "a", "--repo", "ftp://site"])
        config = self.parse(["--package", "a", "--repo", "http://x.org/p/"])
        self.assertEqual(config["repo"], "http://x.org/p")

    def test_test_mode_file(self):
        """В тестовом режиме проверяется файл."""
        with self.assertRaises(ToolError):
            self.parse(["--package", "A", "--test", "--repo", "no.txt"])
        with self.assertRaises(ToolError):
            self.parse(["--package", "A", "--test", "--repo", HERE])
        with self.assertRaises(ToolError):
            self.parse(["--package", "A", "--test"])

    def test_bad_filter(self):
        """Фильтр не может быть пустым или входить в имя пакета."""
        with self.assertRaises(ToolError):
            self.parse(["--package", "abc", "--filter", ""])
        with self.assertRaises(ToolError):
            self.parse(["--package", "abc", "--filter", "b"])

    def test_show_config(self):
        """Параметры печатаются как ключ = значение."""
        out = io.StringIO()
        config = self.parse(["--package", "abc"])
        with redirect_stdout(out):
            depgraph.show_config(config)
        self.assertIn("package = abc", out.getvalue())
        self.assertIn("filter = <не задано>", out.getvalue())

    def test_main_error_code(self):
        """При ошибке main возвращает 1 и пишет в stderr."""
        code, _, err = run_main(["--package", "abc", "--depth", "x"])
        self.assertEqual(code, EXPECTED_BAD_CODE)
        self.assertTrue(err.startswith("Ошибка:"))

    def test_argparse_error(self):
        """Неизвестный параметр останавливает argparse с кодом 2."""
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                depgraph.main(["--nope"])
        self.assertEqual(caught.exception.code, EXPECTED_ARGPARSE_CODE)


if __name__ == "__main__":
    unittest.main()
