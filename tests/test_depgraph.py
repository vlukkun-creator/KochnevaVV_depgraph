"""Тесты для инструмента depgraph."""
import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
import urllib.error
from unittest import mock

import depgraph
from depgraph import ToolError

HERE = os.path.dirname(os.path.abspath(__file__))
REPOS = os.path.join(HERE, "repos")
EXPECTED_DEFAULT_DEPTH = 3
EXPECTED_BAD_CODE = 1
EXPECTED_ARGPARSE_CODE = 2
NOT_FOUND = 404
SERVER_ERROR = 500


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


class RequirementTest(unittest.TestCase):
    """Разбор строк зависимостей и работа с репозиторием."""

    def test_normalize(self):
        """Имя приводится к нижнему регистру, ._ меняются на дефис."""
        self.assertEqual(depgraph.normalize_name("Zope.Interface_X"),
                         "zope-interface-x")

    def test_parse_simple(self):
        """Из строки берется только имя пакета."""
        line = "urllib3<3,>=1.21.1"
        self.assertEqual(depgraph.parse_requirement(line), "urllib3")
        line = "Jinja2>=3.1.2 ; python_version >= '3'"
        self.assertEqual(depgraph.parse_requirement(line), "jinja2")
        line = "PySocks!=1.5.7 ; extra == 'socks'"
        self.assertIsNone(depgraph.parse_requirement(line))
        self.assertIsNone(depgraph.parse_requirement("???"))

    def test_read_requirements(self):
        """Если зависимостей нет, получаем пустой список."""
        self.assertEqual(depgraph.read_requirements(
            {"info": {"requires_dist": None}}), [])
        with self.assertRaises(ToolError):
            depgraph.read_requirements({"data": 1})

    def test_direct_dependencies(self):
        """Прямые зависимости берутся без повторов и без extra."""
        data = {"info": {"requires_dist": [
            "charset_normalizer<4,>=2", "idna<4,>=2.5",
            "idna>=2", "PySocks>=1.5.6 ; extra == 'socks'",
        ]}}
        with mock.patch("depgraph.fetch_json", return_value=data) as fake:
            names = depgraph.get_direct_dependencies("http://r", "requests")
        fake.assert_called_once_with("http://r/requests/json")
        self.assertEqual(names, ["charset-normalizer", "idna"])

    def test_fetch_json_ok(self):
        """Правильный ответ превращается в словарь."""
        answer = mock.MagicMock()
        answer.__enter__.return_value.read.return_value = b'{"a": 1}'
        with mock.patch("urllib.request.urlopen", return_value=answer):
            self.assertEqual(depgraph.fetch_json("http://x"), {"a": 1})

    def test_fetch_json_bad_data(self):
        """Не JSON в ответе - это ошибка."""
        answer = mock.MagicMock()
        answer.__enter__.return_value.read.return_value = b"<html>"
        with mock.patch("urllib.request.urlopen", return_value=answer):
            with self.assertRaises(ToolError):
                depgraph.fetch_json("http://x")

    def test_fetch_json_errors(self):
        """Ошибки сети и сервера превращаются в ToolError."""
        not_found = urllib.error.HTTPError("u", NOT_FOUND, "x", {}, None)
        server = urllib.error.HTTPError("u", SERVER_ERROR, "x", {}, None)
        for error in (not_found, server, urllib.error.URLError("dns")):
            with mock.patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(ToolError):
                    depgraph.fetch_json("http://x")

    def test_main_prints_dependencies(self):
        """На втором этапе main печатает прямые зависимости."""
        with mock.patch("depgraph.get_direct_dependencies",
                        return_value=["idna", "certifi"]):
            code, out, _ = run_main(["--package", "Requests"])
        self.assertEqual(code, 0)
        self.assertIn("idna", out)
        self.assertIn("requests", out)

    def test_test_mode_not_ready(self):
        """Тестовый режим на этом этапе еще не готов."""
        code, _, err = run_main(
            ["--package", "A", "--test", "--repo", repo_path("simple.txt")])
        self.assertEqual(code, EXPECTED_BAD_CODE)
        self.assertIn("следующем этапе", err)


if __name__ == "__main__":
    unittest.main()
