import os
import time
from contextlib import asynccontextmanager, contextmanager

import pymysql
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from pymysql.cursors import DictCursor


def _config() -> dict:
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "3306")),
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "database": os.environ["DB_NAME"],
        "cursorclass": DictCursor,
        "autocommit": True,
        "connect_timeout": 5,
    }


@contextmanager
def conexao():
    con = pymysql.connect(**_config())
    try:
        yield con
    finally:
        con.close()


def aguardar_banco(tentativas: int = 30, intervalo: float = 2.0) -> None:
    for n in range(1, tentativas + 1):
        try:
            with conexao():
                return
        except pymysql.err.OperationalError:
            print(f"[api] MySQL indisponível (tentativa {n}/{tentativas})", flush=True)
            time.sleep(intervalo)
    raise RuntimeError("MySQL não respondeu a tempo")


@asynccontextmanager
async def lifespan(_: FastAPI):
    aguardar_banco()
    yield


app = FastAPI(title="API de Tarefas + MySQL", version="1.1.0", lifespan=lifespan)


class TarefaEntrada(BaseModel):
    titulo: str = Field(min_length=1, max_length=120)


class TarefaAtualizacao(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=120)
    concluida: bool | None = None

    @model_validator(mode="after")
    def pelo_menos_um_campo(self):
        if self.titulo is None and self.concluida is None:
            raise ValueError("informe ao menos um campo: titulo ou concluida")
        return self


class Tarefa(BaseModel):
    id: int
    titulo: str
    concluida: bool


COLUNAS = "id, titulo, concluida"


def _buscar(cur, tarefa_id: int) -> dict | None:
    cur.execute(f"SELECT {COLUNAS} FROM tarefas WHERE id = %s", (tarefa_id,))
    return cur.fetchone()


def _nao_encontrada(tarefa_id: int) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"Tarefa {tarefa_id} não encontrada")


@app.get("/saude")
def saude():
    try:
        with conexao() as con, con.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            return {"api": "ok", "banco": "ok" if cur.fetchone()["ok"] == 1 else "falha"}
    except pymysql.err.MySQLError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"banco indisponível: {exc}")


@app.get("/tarefas", response_model=list[Tarefa])
def listar_tarefas():
    with conexao() as con, con.cursor() as cur:
        cur.execute(f"SELECT {COLUNAS} FROM tarefas ORDER BY id")
        return cur.fetchall()


@app.post("/tarefas", response_model=Tarefa, status_code=status.HTTP_201_CREATED)
def criar_tarefa(entrada: TarefaEntrada):
    with conexao() as con, con.cursor() as cur:
        cur.execute("INSERT INTO tarefas (titulo) VALUES (%s)", (entrada.titulo,))
        return {"id": cur.lastrowid, "titulo": entrada.titulo, "concluida": False}


@app.get(
    "/tarefas/{tarefa_id}",
    response_model=Tarefa,
    responses={404: {"description": "Tarefa não encontrada"}},
)
def obter_tarefa(tarefa_id: int):
    with conexao() as con, con.cursor() as cur:
        tarefa = _buscar(cur, tarefa_id)
    if tarefa is None:
        raise _nao_encontrada(tarefa_id)
    return tarefa


@app.patch(
    "/tarefas/{tarefa_id}",
    response_model=Tarefa,
    responses={404: {"description": "Tarefa não encontrada"}},
)
def atualizar_tarefa(tarefa_id: int, entrada: TarefaAtualizacao):
    campos = entrada.model_dump(exclude_none=True)
    sets = ", ".join(f"{coluna} = %s" for coluna in campos)
    with conexao() as con, con.cursor() as cur:
        if _buscar(cur, tarefa_id) is None:
            raise _nao_encontrada(tarefa_id)
        cur.execute(f"UPDATE tarefas SET {sets} WHERE id = %s", (*campos.values(), tarefa_id))
        return _buscar(cur, tarefa_id)
