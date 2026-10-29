"""Cross-app checks for the refactor; never opens the user's database."""

import ast
import importlib
import inspect
from pathlib import Path
from typing import get_type_hints

from django.apps import apps
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.state import ProjectState
from django.test import SimpleTestCase


class BackendVerificationTests(SimpleTestCase):
    def test_model_refactor_requires_no_schema_migrations(self) -> None:
        loader = MigrationLoader(None, ignore_no_migrations=True)
        detector = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps))
        project_apps = {"menu", "cart", "orders", "users", "recommendation"}
        changes = detector.changes(graph=loader.graph)
        self.assertEqual(
            {app: migrations for app, migrations in changes.items() if app in project_apps}, {}
        )

    def test_active_backend_annotations_are_complete_and_resolve(self) -> None:
        root = Path(__file__).resolve().parents[2]
        checked = 0

        for app in ("menu", "cart", "orders", "users", "recommendation", "config"):
            for source in sorted((root / app).rglob("*.py")):
                if source.name.startswith("test") or any(
                    part in source.parts for part in ("tests", "migrations", "__pycache__")
                ):
                    continue

                tree = ast.parse(source.read_text(encoding="utf-8-sig"))
                functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]

                for node in functions:
                    with self.subTest(source=source.name, function=node.name):
                        self.assertIsNotNone(node.returns)
                        arguments = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                        arguments += [
                            argument
                            for argument in (node.args.vararg, node.args.kwarg)
                            if argument is not None
                        ]

                        for argument in arguments:
                            if argument.arg not in ("self", "cls"):
                                self.assertIsNotNone(argument.annotation)

                if not functions:
                    continue

                # Config entrypoints have no source functions, so credentials/settings
                # profiles are not imported by this introspection pass.
                module = importlib.import_module(
                    ".".join(source.relative_to(root).with_suffix("").parts)
                )
                namespace = dict(vars(module))
                candidates = []

                for value in vars(module).values():
                    if getattr(value, "__module__", None) != module.__name__:
                        continue

                    if inspect.isfunction(value):
                        candidates.append(value)
                    elif inspect.isclass(value):
                        get_type_hints(value, globalns=namespace)

                        for member in vars(value).values():
                            if isinstance(member, (staticmethod, classmethod)):
                                candidates.append(member.__func__)
                            elif isinstance(member, property) and member.fget is not None:
                                candidates.append(member.fget)
                            elif inspect.isfunction(member):
                                candidates.append(member)

                for candidate in candidates:
                    candidate = inspect.unwrap(candidate)

                    if (
                        candidate.__name__ == "__annotate__"
                        or candidate.__module__ != module.__name__
                    ):
                        continue

                    with self.subTest(callable=candidate.__qualname__):
                        self.assertIn("return", get_type_hints(candidate, globalns=namespace))

                    checked += 1

        self.assertGreater(checked, 200)
