from fastapi import FastAPI, status
from pydantic import BaseModel, Field

app = FastAPI(title="API de Tarefas", version="1.0.0")

_tarefas: list[dict] = []


class TarefaEntrada(BaseModel):
    titulo: str = Field(min_length=1, max_length=120)


class Tarefa(BaseModel):
    id: int
    titulo: str


@app.get("/tarefas", response_model=list[Tarefa])
def listar_tarefas():
    return _tarefas


@app.post("/tarefas", response_model=Tarefa, status_code=status.HTTP_201_CREATED)
def criar_tarefa(entrada: TarefaEntrada):
    tarefa = {"id": len(_tarefas) + 1, "titulo": entrada.titulo}
    _tarefas.append(tarefa)
    return tarefa
