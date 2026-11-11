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
GRAPH_SIZE = 4


def fake_deps(source, name):
    """Подставляет зависимости вместо запроса в интернет."""
    return {"requests": ["idna"]}.get(name, [])


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


class TestRepoTest(unittest.TestCase):
    """Чтение тестового репозитория."""

    def test_read(self):
        """Файл читается в словарь."""
        repo = depgraph.read_test_repo(repo_path("simple.txt"))
        self.assertEqual(repo["A"], ["B", "C"])
        self.assertEqual(repo["D"], [])

    def test_bad_files(self):
        """Неверные файлы дают ошибку."""
        for name in ("bad_no_colon.txt", "bad_name.txt",
                     "bad_duplicate.txt"):
            with self.assertRaises(ToolError):
                depgraph.read_test_repo(repo_path(name))

    def test_unknown_package(self):
        """Пакета нет в файле - ошибка."""
        code, _, err = run_main(
            ["--package", "Z", "--test", "--repo", repo_path("simple.txt")])
        self.assertEqual(code, EXPECTED_BAD_CODE)
        self.assertIn("не найден", err)

    def test_comment_line(self):
        """Комментарии и пустые строки пропускаются."""
        self.assertIsNone(depgraph.parse_test_line(1, "# text"))
        self.assertIsNone(depgraph.parse_test_line(1, "   "))
        self.assertEqual(depgraph.parse_test_line(1, "A: B B"), ("A", ["B"]))


class BuildGraphTest(unittest.TestCase):
    """Обход графа в ширину."""

    def graph(self, name, root="A", depth=10, substring=None):
        """Строит граф по тестовому файлу."""
        repo = depgraph.read_test_repo(repo_path(name))
        return depgraph.build_graph(
            root, depgraph.test_deps, repo, depth, substring)

    def test_diamond(self):
        """У ромба четыре пакета, D один раз."""
        graph = self.graph("simple.txt")
        self.assertEqual(len(graph), GRAPH_SIZE)
        self.assertEqual(list(graph), ["A", "B", "C", "D"])

    def test_depth(self):
        """Глубина ограничивает обход."""
        graph = self.graph("chain.txt", depth=2)
        self.assertEqual(list(graph), ["A", "B", "C"])
        self.assertEqual(graph["C"], [])

    def test_filter(self):
        """Пакеты с подстрокой не попадают в граф."""
        graph = self.graph("simple.txt", substring="C")
        self.assertEqual(list(graph), ["A", "B", "D"])
        self.assertEqual(graph["A"], ["B"])

    def test_cycle(self):
        """Цикл не приводит к бесконечному обходу."""
        graph = self.graph("cycle.txt")
        self.assertEqual(graph, {"A": ["B"], "B": ["C"], "C": ["A"]})

    def test_self_cycle(self):
        """Пакет, зависящий от самого себя, тоже обрабатывается."""
        graph = self.graph("self_cycle.txt")
        self.assertEqual(graph["A"], ["A", "B"])

    def test_no_deps(self):
        """У пакета без зависимостей один узел."""
        self.assertEqual(self.graph("no_deps.txt"), {"A": []})

    def test_long_chain_no_recursion(self):
        """Очень длинная цепочка не ломает обход (рекурсии нет)."""
        size = 5000
        chain = {f"N{i}": [f"N{i + 1}"] for i in range(size)}
        graph = depgraph.build_graph(
            "N0", depgraph.test_deps, chain, size, None)
        self.assertEqual(len(graph), size + 1)

    def test_real_source(self):
        """Для настоящего репозитория зависимости берутся из PyPI."""
        graph = depgraph.build_graph(
            "requests", fake_deps, "http://r", 3, None)
        self.assertEqual(graph, {"requests": ["idna"], "idna": []})

    def test_main_output(self):
        """main печатает граф в тестовом режиме."""
        code, out, _ = run_main(
            ["--package", "A", "--test", "--repo", repo_path("cycle.txt")])
        self.assertEqual(code, 0)
        self.assertIn('"C" -> "A"', out)


class ReverseTest(unittest.TestCase):
    """Обратные зависимости."""

    def test_reverse_edges(self):
        """Ребра переворачиваются."""
        repo = depgraph.read_test_repo(repo_path("simple.txt"))
        self.assertEqual(depgraph.reverse_edges(repo),
                         {"B": ["A"], "C": ["A"], "D": ["B", "C"]})

    def test_main_reverse(self):
        """Для D зависят B, C и A."""
        code, out, _ = run_main(
            ["--package", "D", "--test", "--reverse",
             "--repo", repo_path("simple.txt")])
        self.assertEqual(code, 0)
        self.assertIn("D <- B C", out)
        self.assertIn("B <- A", out)
        self.assertIn("зависят от D: 3", out)

    def test_reverse_depth_and_filter(self):
        """Глубина и фильтр работают и для обратных зависимостей."""
        code, out, _ = run_main(
            ["--package", "D", "--test", "--reverse", "--depth", "1",
             "--repo", repo_path("simple.txt")])
        self.assertEqual(code, 0)
        self.assertNotIn("B <- A", out)
        code, out, _ = run_main(
            ["--package", "D", "--test", "--reverse", "--filter", "B",
             "--repo", repo_path("simple.txt")])
        self.assertNotIn("B", out.replace("Обратные", ""))

    def test_reverse_nobody(self):
        """Если от пакета никто не зависит, пишем об этом."""
        code, out, _ = run_main(
            ["--package", "A", "--test", "--reverse",
             "--repo", repo_path("simple.txt")])
        self.assertEqual(code, 0)
        self.assertIn("никто не зависит", out)

    def test_reverse_cycle(self):
        """В цикле обратный обход тоже заканчивается."""
        code, out, _ = run_main(
            ["--package", "A", "--test", "--reverse",
             "--repo", repo_path("cycle.txt")])
        self.assertEqual(code, 0)
        self.assertIn("A <- C", out)
        self.assertIn("зависят от A: 3", out)

    def test_reverse_real_mode(self):
        """В реальном режиме обратные зависимости дают понятную ошибку."""
        code, _, err = run_main(["--package", "requests", "--reverse"])
        self.assertEqual(code, EXPECTED_BAD_CODE)
        self.assertIn("--test", err)


class PictureTest(unittest.TestCase):
    """Описание на языке D2 и ASCII-дерево."""

    def test_d2(self):
        """Ребра записаны в кавычках, одиночный узел объявлен отдельно."""
        text = depgraph.d2_text({"a.b": ["c"], "c": [], "z": []})
        self.assertIn('"a.b" -> "c"', text)
        self.assertIn('\n"z"', text)
        self.assertTrue(text.startswith("direction: right"))

    def test_tree(self):
        """Дерево ромба рисуется ASCII-символами."""
        graph = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
        lines = depgraph.tree_lines(graph, "A", 5)
        self.assertEqual(lines, [
            "A", "|-- B", "|   `-- D", "`-- C", "    `-- D"])

    def test_tree_cycle(self):
        """В дереве цикл помечается и не раскрывается."""
        graph = {"A": ["B"], "B": ["A"]}
        lines = depgraph.tree_lines(graph, "A", 10)
        self.assertEqual(lines[-1], "    `-- A (цикл)")

    def test_tree_depth(self):
        """Дерево не глубже заданного уровня."""
        graph = {"A": ["B"], "B": ["C"], "C": []}
        self.assertEqual(depgraph.tree_lines(graph, "A", 1),
                         ["A", "`-- B"])

    def test_main_ascii(self):
        """С параметром --ascii после D2 печатается дерево."""
        argv = ["--package", "A", "--test", "--repo",
                repo_path("simple.txt")]
        _, out, _ = run_main(argv)
        self.assertNotIn("ASCII-дерево", out)
        _, out, _ = run_main(argv + ["--ascii"])
        self.assertIn("ASCII-дерево", out)
        self.assertIn("|-- B", out)


if __name__ == "__main__":
    unittest.main()
