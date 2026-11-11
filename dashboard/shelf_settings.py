"""Profile-local UI preferences. Never grants initial or version-save consent."""
import json
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

View = Literal['together', 'library', 'gallery']


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    trash_retention_days: Literal[30, 60] = 60
    auto_cleanup: bool = True
    timezone: str = Field(default='auto', min_length=1, max_length=100)
    hour_cycle: Literal['auto', '12', '24'] = 'auto'
    date_format: Literal['short', 'medium', 'long', 'iso'] = 'medium'
    default_view: View = 'together'
    enabled_views: list[View] = Field(default_factory=lambda: ['together', 'library', 'gallery'], min_length=1, max_length=3)
    generate_metadata: bool = True
    context_messages: int = 10

    @field_validator('trash_retention_days', mode='before')
    @classmethod
    def exact_retention(cls, value):
        if type(value) is not int:
            raise ValueError('Retention must be 30 or 60 days')
        return value

    @field_validator('timezone')
    @classmethod
    def known_timezone(cls, value):
        if value != 'auto':
            try:
                ZoneInfo(value)
            except (ValueError, ZoneInfoNotFoundError):
                raise ValueError('Use auto or an IANA timezone') from None
        return value

    @field_validator('context_messages')
    @classmethod
    def context_preset(cls, value):
        if value not in (5, 10, 20, 50):
            raise ValueError('Context must be 5, 10, 20 or 50')
        return value

    @model_validator(mode='after')
    def usable_views(self):
        if len(set(self.enabled_views)) != len(self.enabled_views) or self.default_view not in self.enabled_views:
            raise ValueError('Default view must be enabled; views must be unique')
        return self


def initialize(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS shelf_settings (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')


def read(conn):
    row = conn.execute('SELECT payload FROM shelf_settings WHERE id=1').fetchone()
    if row:
        return Settings.model_validate_json(row[0]).model_dump()
    defaults = Settings().model_dump()
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'").fetchone():
        legacy = conn.execute("SELECT value FROM settings WHERE key='previous_exchanges'").fetchone()
        if legacy and legacy[0] in (5,10,20,50):
            defaults['context_messages'] = legacy[0]
    return defaults


def save(conn, payload):
    before = read(conn)
    values = Settings.model_validate({**before, **payload}).model_dump()
    conn.execute('INSERT INTO shelf_settings VALUES (1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (json.dumps(values),))
    if before['trash_retention_days'] != values['trash_retention_days']:
        conn.execute("UPDATE entry_lifecycle SET delete_after=trashed_at+? WHERE state='trash'", (values['trash_retention_days'] * 86400,))
        conn.execute("UPDATE entries SET revision=revision+1 WHERE id IN (SELECT entry_id FROM entry_lifecycle WHERE state='trash')")
    return values
