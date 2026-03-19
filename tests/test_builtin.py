"""Tests de tools builtin (README: get_time)."""

import re

import pytest

from amanda_ia.tools import builtin


class TestGetTime:
    """Tests para get_time - salida esperada: HH:MM:SS - DD/MM/YYYY."""

    def test_returns_string(self):
        result = builtin.get_time()
        assert isinstance(result, str)

    def test_format_hh_mm_ss_date(self):
        """Formato esperado: 14:30:00 - 10/03/2025."""
        result = builtin.get_time()
        assert re.match(r"\d{2}:\d{2}:\d{2} - \d{2}/\d{2}/\d{4}", result), (
            f"get_time debe devolver HH:MM:SS - DD/MM/YYYY, obtuvo: {result}"
        )
