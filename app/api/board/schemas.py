from pydantic import BaseModel, Field


class BoardCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    sort_order: int = 0
    icon: str = Field(default="", max_length=24)
    is_active: bool = True
    parent_board_id: int | None = None
    tab_label: str = Field(default="", max_length=40)


class BoardReorder(BaseModel):
    board_ids: list[int] = Field(min_length=1)


class BoardUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=2, max_length=60)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None
    icon: str | None = Field(default=None, max_length=24)
    is_active: bool | None = None
    parent_board_id: int | None = None
    tab_label: str | None = Field(default=None, max_length=40)


class BoardTabCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    tab_label: str = Field(default="", max_length=40)
    description: str = Field(default="", max_length=500)
    sort_order: int = 0
    is_active: bool = True


class BoardTabUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=2, max_length=60)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    tab_label: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None
    is_active: bool | None = None


class PostCreate(BaseModel):
    title: str = Field(default="", max_length=250)


class PostUpdate(BaseModel):
    title: str = Field(default="", max_length=250)
    body_html: str = ""
    is_pinned: bool = False
    status: str = Field(default="published")
    board_id: int | None = None


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class CommentUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
