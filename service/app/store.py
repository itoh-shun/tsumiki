"""タスクのストア層。SQLite への CRUD を担う。"""

import sqlite3
from datetime import datetime, timezone

from app.models import (
    Project,
    ProjectCreate,
    ProjectUpdate,
    State,
    Task,
    TaskCreate,
    TaskUpdate,
    assert_transition,
)


class TaskNotFound(Exception):
    """指定した id のタスクが存在しないときに送出する。"""


class ProjectNotFound(Exception):
    """指定した id のプロジェクトが存在しないときに送出する。"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        body=row["body"],
        state=State(row["state"]),
        project_id=row["project_id"],
        context=row["context"],
        due=row["due"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
    )


class TaskStore:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add(self, data: TaskCreate) -> Task:
        now = _now()
        cur = self._conn.execute(
            """
            INSERT INTO tasks (title, body, state, project_id, context, due, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.title,
                data.body,
                data.state.value,
                data.project_id,
                data.context,
                data.due,
                now,
                now,
            ),
        )
        self._conn.commit()
        return self.get(cur.lastrowid)  # type: ignore[arg-type]

    def get(self, task_id: int) -> Task | None:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_task(row)

    def list(
        self,
        state: State | None = None,
        context: str | None = None,
        project_id: int | None = None,
        due_before: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Task]:
        clauses: list[str] = []
        params: list = []
        if state is not None:
            clauses.append("state = ?")
            params.append(state.value)
        if context is not None:
            clauses.append("context = ?")
            params.append(context)
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        if due_before is not None:
            clauses.append("due IS NOT NULL AND due < ?")
            params.append(due_before)

        sql = "SELECT * FROM tasks"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        # due が NULL のものを最後にするため CASE で明示的にソート
        sql += """
            ORDER BY
                CASE state
                    WHEN 'inbox' THEN 0
                    WHEN 'next' THEN 1
                    WHEN 'waiting' THEN 2
                    WHEN 'someday' THEN 3
                    WHEN 'done' THEN 4
                END,
                CASE WHEN due IS NULL THEN 1 ELSE 0 END,
                due ASC,
                created_at ASC,
                id ASC
        """
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            # OFFSET だけを指定したい場合、SQLite では LIMIT -1 が必要
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)

        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_task(r) for r in rows]

    def update(self, task_id: int, data: TaskUpdate) -> Task:
        current = self.get(task_id)
        if current is None:
            raise TaskNotFound(f"task {task_id} not found")

        if data.state is not None:
            # 同一状態への遷移も含め、T3 の許可表に厳密に従う
            assert_transition(current.state, data.state)

        fields: dict = {}
        for field in ("title", "body", "state", "project_id", "context", "due"):
            value = getattr(data, field)
            if value is not None:
                fields[field] = value.value if isinstance(value, State) else value

        # completed_at は「エンドポイント由来」ではなく state 由来の不変条件として扱う:
        # completed_at が非 NULL であることと state == done であることは常に一致させる。
        if data.state is not None:
            if data.state == State.done:
                fields["completed_at"] = _now()
            elif current.state == State.done:
                fields["completed_at"] = None

        # 変更対象のフィールドが無くても updated_at は必ず更新する
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [task_id]
        self._conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", params)
        self._conn.commit()
        return self.get(task_id)  # type: ignore[return-value]

    def complete(self, task_id: int) -> Task:
        # done への遷移と completed_at の設定は update() に一本化してある。
        # 同一状態(done→done)も T3 の許可表どおり拒否される(= 再 complete は 409)。
        return self.update(task_id, TaskUpdate(state=State.done))

    def delete(self, task_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()
        return cur.rowcount > 0


def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        note=row["note"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ProjectStore:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add(self, data: ProjectCreate) -> Project:
        now = _now()
        cur = self._conn.execute(
            "INSERT INTO projects (name, note, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (data.name, data.note, now, now),
        )
        self._conn.commit()
        return self.get(cur.lastrowid)  # type: ignore[arg-type]

    def get(self, project_id: int) -> Project | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_project(row)

    def list(self) -> list[Project]:
        rows = self._conn.execute("SELECT * FROM projects ORDER BY name ASC").fetchall()
        return [_row_to_project(r) for r in rows]

    def update(self, project_id: int, data: ProjectUpdate) -> Project:
        current = self.get(project_id)
        if current is None:
            raise ProjectNotFound(f"project {project_id} not found")

        fields: dict = {}
        for field in ("name", "note"):
            value = getattr(data, field)
            if value is not None:
                fields[field] = value

        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [project_id]
        self._conn.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", params)
        self._conn.commit()
        return self.get(project_id)  # type: ignore[return-value]

    def delete(self, project_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self._conn.commit()
        return cur.rowcount > 0
