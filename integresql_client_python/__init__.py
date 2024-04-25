__all__ = ["IntegreSQL", "DBInfo", "Database", "Template"]

import hashlib
import http.client
import json
import logging
import os
import pathlib
from typing import List, NoReturn, Optional, Union

import requests

from . import errors

logger = logging.getLogger("integresql-client-python")

__version__ = "0.9.2"
ENV_INTEGRESQL_CLIENT_BASE_URL = "INTEGRESQL_CLIENT_BASE_URL"
ENV_INTEGRESQL_CLIENT_API_VERSION = "INTEGRESQL_CLIENT_API_VERSION"
DEFAULT_CLIENT_BASE_URL = "http://integresql:5000/api"
DEFAULT_CLIENT_API_VERSION = "v1"


class DBInfo:
    __slots__ = ("db_id", "tpl_hash", "host", "port", "user", "password", "name")

    def __init__(self, info: dict) -> None:
        self.db_id = info.get("id")
        self.tpl_hash = info["database"]["templateHash"]

        info = info["database"]["config"]
        self.host = info["host"]
        self.port = info["port"]
        self.user = info["username"]
        self.password = info["password"]
        self.name = info["database"]

    def __str__(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    __repr__ = __str__


class TemplateHash:
    BUFFER_SIZE = 4 * 1024

    def __init__(
        self,
        template: Union[str, List[str], pathlib.PurePath, List[pathlib.PurePath], None],
    ) -> None:
        if not isinstance(template, (list, tuple)):
            template = [template]
        self.templates = template

        mhash = hashlib.md5()
        for template in self.templates:
            if not isinstance(template, pathlib.PurePath):
                template = pathlib.Path(template)

            if not template.exists():
                raise RuntimeError(f"Path {template} doesn't exists")

            if not template.is_dir():
                raise RuntimeError(f"Path {template} must be a directory")

            hashed = self.calculate(template)
            mhash.update(hashed.encode())

        self.hash = mhash.hexdigest()

    def __str__(self) -> str:
        return self.hash

    @classmethod
    def calculate(cls, path: pathlib.Path) -> str:
        template_hash = hashlib.md5()
        items = list(path.rglob("*"))
        items.sort()
        for item in items:
            if item.is_dir():
                continue

            item_hash = hashlib.md5()
            with item.open("rb") as fh:
                while True:
                    data = fh.read(cls.BUFFER_SIZE)
                    item_hash.update(data)
                    if len(data) < cls.BUFFER_SIZE:
                        break
            template_hash.update(item_hash.hexdigest().encode())

        return template_hash.hexdigest()


class Database:
    def __init__(self, integresql: "IntegreSQL") -> None:
        self.integresql = integresql
        self.dbinfo = None

    def destroy(self, db_id: Union[int, DBInfo]) -> NoReturn:
        """
        Release the database back to the pool so it can be reused.
        The database will be recreated to the template image.
        """

        logger.debug(f"Database: destroy: {self.dbinfo}")

        if isinstance(db_id, DBInfo):
            db_id = db_id.db_id

        if db_id is None:
            raise errors.IntegreSQLError("Invalid database id")

        rsp = self.integresql.request(
            "POST", f"/templates/{self.integresql.tpl_hash}/tests/{db_id}/recreate"
        )
        if rsp.status_code == http.client.NO_CONTENT:
            return

        if rsp.status_code == http.client.NOT_FOUND:
            raise errors.NotFound(rsp.text)
        elif rsp.status_code == http.client.BAD_REQUEST:
            raise errors.BadDatabaseID()
        elif rsp.status_code == http.client.SERVICE_UNAVAILABLE:
            raise errors.ManagerNotReady()
        elif rsp.status_code == http.client.LOCKED:
            raise errors.DatabaseInUse()
        else:
            raise errors.IntegreSQLError(
                f"Received unexpected HTTP status {rsp.status_code}"
            )

    def free(self, db_id: Union[int, DBInfo]) -> NoReturn:
        """
        Release the database back to the pool so it can be reused.
        The database retains its current state.
        """

        logger.debug(f"Database: free: {self.dbinfo}")

        if isinstance(db_id, DBInfo):
            db_id = db_id.db_id

        if db_id is None:
            raise errors.IntegreSQLError("Invalid database id")

        rsp = self.integresql.request(
            "POST", f"/templates/{self.integresql.tpl_hash}/tests/{db_id}/unlock"
        )
        if rsp.status_code == http.client.NO_CONTENT:
            return

        if rsp.status_code == http.client.NOT_FOUND:
            raise errors.NotFound(rsp.text)
        elif rsp.status_code == http.client.BAD_REQUEST:
            raise errors.BadDatabaseID()
        elif rsp.status_code == http.client.SERVICE_UNAVAILABLE:
            raise errors.ManagerNotReady()
        elif rsp.status_code == http.client.LOCKED:
            raise errors.DatabaseInUse()
        else:
            raise errors.IntegreSQLError(
                f"Received unexpected HTTP status {rsp.status_code}"
            )

    def open(self) -> DBInfo:
        logger.debug(f"Database: open: {self.dbinfo}")

        rsp = self.integresql.request(
            "GET", f"/templates/{self.integresql.tpl_hash}/tests"
        )
        if rsp.status_code == http.client.OK:
            return DBInfo(rsp.json())

        if rsp.status_code == http.client.NOT_FOUND:
            raise errors.TemplateNotFound()
        elif rsp.status_code == http.client.GONE:
            raise errors.DatabaseDiscarded()
        elif rsp.status_code == http.client.SERVICE_UNAVAILABLE:
            raise errors.ManagerNotReady()
        else:
            raise errors.IntegreSQLError(
                f"Received unexpected HTTP status {rsp.status_code}"
            )

    def mark_unmodified(self, db_id: Union[int, DBInfo]) -> NoReturn:
        logger.debug(f"Database: mark_unmodified: {db_id}")

        if isinstance(db_id, DBInfo):
            db_id = db_id.db_id

        if db_id is None:
            raise errors.IntegreSQLError("Invalid database id")

        rsp = self.integresql.request(
            "DELETE", f"/templates/{self.integresql.tpl_hash}/tests/{db_id}"
        )
        if rsp.status_code == http.client.NO_CONTENT:
            return

        if rsp.status_code == http.client.NOT_FOUND:
            raise errors.TemplateNotFound()
        elif rsp.status_code == http.client.SERVICE_UNAVAILABLE:
            raise errors.ManagerNotReady()
        else:
            raise errors.IntegreSQLError(
                f"Received unexpected HTTP status {rsp.status_code}"
            )

    def __enter__(self) -> DBInfo:
        logger.debug(f"Database: __enter__: {self.dbinfo}")

        self.dbinfo = self.open()
        return self.dbinfo

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger.debug(f"Database: __exit__: {self.dbinfo}")

        self.destroy(self.dbinfo.db_id)


class Template:
    def __init__(self, integresql: "IntegreSQL") -> None:
        self.integresql = integresql
        self.dbinfo = None

    def initialize(self) -> "Template":
        logger.debug("Template: initialize")

        rsp = self.integresql.request(
            "POST", "/templates", payload={"hash": str(self.integresql.tpl_hash)}
        )
        if rsp.status_code == http.client.OK:
            self.dbinfo = DBInfo(rsp.json())
            return self
        elif rsp.status_code == http.client.LOCKED:
            return self

        if rsp.status_code == http.client.SERVICE_UNAVAILABLE:
            raise errors.ManagerNotReady()
        else:
            raise errors.IntegreSQLError(
                f"Received unexpected HTTP status {rsp.status_code}"
            )

    def finalize(self) -> NoReturn:
        logger.debug(f"Template: finalize: {self.dbinfo}")

        rsp = self.integresql.request("PUT", f"/templates/{self.integresql.tpl_hash}")
        if rsp.status_code == http.client.NO_CONTENT:
            return

        if rsp.status_code == http.client.NOT_FOUND:
            raise errors.TemplateNotFound()
        elif rsp.status_code == http.client.SERVICE_UNAVAILABLE:
            raise errors.ManagerNotReady()
        else:
            raise errors.IntegreSQLError(
                f"Received unexpected HTTP status {rsp.status_code}"
            )

    def discard(self) -> NoReturn:
        logger.debug(f"Template: discard: {self.dbinfo}")

        return self.integresql.discard_template(self.integresql.tpl_hash)

    def get_database(self) -> Database:
        logger.debug(f"Template: get_database: {self.dbinfo}")

        return Database(self.integresql)

    def __enter__(self) -> DBInfo:
        logger.debug(f"Template: __enter__: {self.dbinfo}")

        return self.dbinfo

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger.debug(f"Template: __exit__: {self.dbinfo}")

        self.finalize()


class IntegreSQL:
    def __init__(
        self,
        tpl_directory: Union[
            TemplateHash, str, List[str], pathlib.PurePath, List[pathlib.PurePath], None
        ] = None,
        *,
        base_url: Optional[str] = None,
        api_version: Optional[str] = None,
        tpl_name: str | None = None,
    ) -> None:
        if not base_url:
            base_url = os.environ.get(
                ENV_INTEGRESQL_CLIENT_BASE_URL, DEFAULT_CLIENT_BASE_URL
            )
        if not api_version:
            api_version = os.environ.get(
                ENV_INTEGRESQL_CLIENT_API_VERSION, DEFAULT_CLIENT_API_VERSION
            )

        self.base_url = base_url
        self.api_version = api_version
        self._connection = None
        self._tpl_hash = tpl_name
        if tpl_directory:
            self.tpl_hash = tpl_directory

    @property
    def tpl_hash(self) -> Optional[TemplateHash]:
        return self._tpl_hash

    @tpl_hash.setter
    def tpl_hash(
        self,
        value: Union[
            TemplateHash, pathlib.PurePath, str, List[str], List[pathlib.PurePath]
        ],
    ) -> NoReturn:
        if not isinstance(value, TemplateHash):
            value = TemplateHash(value)

        self._tpl_hash = value

    def get_template(self) -> Template:
        logger.debug("IntegreSQL: get_template")

        return Template(self)

    def discard_template(self, tpl_hash: Union[TemplateHash, str]) -> NoReturn:
        logger.debug("IntegreSQL: discard_template")

        rsp = self.request("DELETE", f"/templates/{tpl_hash}")
        if rsp.status_code == http.client.NO_CONTENT:
            return

        if rsp.status_code == http.client.NOT_FOUND:
            raise errors.TemplateNotFound()
        elif rsp.status_code == http.client.SERVICE_UNAVAILABLE:
            raise errors.ManagerNotReady()
        else:
            raise errors.IntegreSQLError(
                f"Received unexpected HTTP status {rsp.status_code}"
            )

    def reset_all_tracking(self) -> NoReturn:
        logger.debug("IntegreSQL: reset_all_tracking")

        rsp = self.request("DELETE", "/admin/templates")
        if rsp.status_code == http.client.NO_CONTENT:
            return

        raise errors.IntegreSQLError(f"failed to reset all tracking: {rsp.content}")

    @property
    def connection(self) -> requests.Session:
        if not self._connection:
            self._connection = requests.Session()

        return self._connection

    def request(
        self,
        method: str,
        path: str,
        *,
        qs: Optional[dict] = None,
        payload: Optional[dict] = None,
    ) -> requests.Response:
        logger.debug("IntegreSQL: request")

        path = path.lstrip("/")
        url = f"{self.base_url}/{self.api_version}/{path}"
        headers = {"content-type": "application/json"}
        json_payload = json.dumps(payload)

        logger.info(
            f"Request {method.upper()} to {url} with qs {qs} and headers {headers} and data {json_payload}"
        )
        rsp = self.connection.request(method, url, qs, json_payload, headers=headers)

        logger.info(
            f"Response from {method.upper()} {url}: [{rsp.status_code}] {rsp.content}"
        )

        return rsp

    def close(self) -> NoReturn:
        logger.debug("IntegreSQL: close")

        self._tpl_hash = None
        if self._connection:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> Template:
        logger.debug("IntegreSQL: __enter__")

        return self.get_template()

    def __exit__(self, exc_type, exc_val, exc_tb) -> NoReturn:
        logger.debug("IntegreSQL: __exit__")

        self.close()
