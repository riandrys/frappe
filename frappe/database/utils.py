# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

from functools import cached_property
from types import NoneType
import typing

import frappe
from frappe.query_builder.builder import MariaDB, Postgres

if typing.TYPE_CHECKING:
	from frappe.query_builder import DocType

Query = str | MariaDB | Postgres
QueryValues = tuple | list | dict | NoneType

EmptyQueryValues = object()
FallBackDateTimeStr = "0001-01-01 00:00:00.000000"


def is_query_type(query: str, query_type: str | tuple[str]) -> bool:
	return query.lstrip().split(maxsplit=1)[0].lower().startswith(query_type)

def table_from_string(table: str) -> "DocType":
	table_name = table.split("`", maxsplit=1)[1].split(".")[0][3:]
	if "`" in table_name:
		return frappe.qb.DocType(table_name=table_name.replace("`", ""))
	else:
		return frappe.qb.DocType(table_name=table_name)

class LazyString:
	def _setup(self) -> None:
		raise NotImplementedError

	@cached_property
	def value(self) -> str:
		return self._setup()

	def __str__(self) -> str:
		return self.value

	def __repr__(self) -> str:
		return f"'{self.value}'"


class LazyDecode(LazyString):
	__slots__ = ()

	def __init__(self, value: str) -> None:
		self._value = value

	def _setup(self) -> None:
		return self._value.decode()


class LazyMogrify(LazyString):
	__slots__ = ()

	def __init__(self, query, values) -> None:
		self.query = query
		self.values = values

	def _setup(self) -> str:
		return frappe.db.mogrify(self.query, self.values)
