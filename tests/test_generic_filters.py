"""Tests for generic filter layer: apply_filters and make_filter_dependency."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy import String, Boolean, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from jm_api.db.base import Base, TimestampedIdBase


# --- Test model ---


class Widget(TimestampedIdBase):
    """Minimal model for testing generic filters."""

    __tablename__ = "widgets"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)


# --- Fixtures ---


@pytest.fixture
def widget_engine():
    engine = sa.create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=sa.pool.StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def widget_session(widget_engine) -> Session:
    session = Session(widget_engine)
    yield session
    session.close()


@pytest.fixture
def widget_factory(widget_session: Session):
    def _create(
        name: str = "widget",
        active: bool = True,
        description: str | None = None,
        create_at: datetime | None = None,
    ) -> Widget:
        w = Widget(name=name, active=active, description=description)
        widget_session.add(w)
        widget_session.flush()
        if create_at is not None:
            widget_session.execute(
                sa.update(Widget).where(Widget.id == w.id).values(create_at=create_at)
            )
        widget_session.commit()
        widget_session.refresh(w)
        return w

    return _create


# --- Tests ---


class TestApplyFiltersExact:
    """EXACT filter type tests."""

    def test_exact_match_string(self, widget_session, widget_factory):
        """EXACT filter on string column returns only matching rows."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        widget_factory(name="alpha")
        widget_factory(name="beta")
        widget_factory(name="alpha")

        config = [FilterField("name", FilterType.EXACT)]
        query = sa.select(Widget)
        filtered = apply_filters(query, Widget, config, {"name": "alpha"})
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 2
        assert all(w.name == "alpha" for w in results)

    def test_exact_match_bool(self, widget_session, widget_factory):
        """EXACT filter on bool column returns only matching rows."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        widget_factory(name="a", active=True)
        widget_factory(name="b", active=False)
        widget_factory(name="c", active=True)

        config = [FilterField("active", FilterType.EXACT, python_type=bool)]
        query = sa.select(Widget)
        filtered = apply_filters(query, Widget, config, {"active": False})
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 1
        assert results[0].name == "b"

    def test_exact_none_skipped(self, widget_session, widget_factory):
        """None value for EXACT filter is ignored (no filtering)."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        widget_factory(name="alpha")
        widget_factory(name="beta")

        config = [FilterField("name", FilterType.EXACT)]
        query = sa.select(Widget)
        filtered = apply_filters(query, Widget, config, {"name": None})
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 2


class TestApplyFiltersIlike:
    """ILIKE filter type tests."""

    def test_ilike_substring_match(self, widget_session, widget_factory):
        """ILIKE matches substring case-insensitively."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        widget_factory(name="a", description="ERROR occurred")
        widget_factory(name="b", description="error found")
        widget_factory(name="c", description="Success")

        config = [FilterField("description", FilterType.ILIKE, param_name="desc_search")]
        query = sa.select(Widget)
        filtered = apply_filters(query, Widget, config, {"desc_search": "error"})
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 2

    def test_ilike_escapes_percent(self, widget_session, widget_factory):
        """ILIKE escapes % wildcard so it matches literally."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        widget_factory(name="a", description="100% complete")
        widget_factory(name="b", description="complete")

        config = [FilterField("description", FilterType.ILIKE, param_name="desc_search")]
        query = sa.select(Widget)
        filtered = apply_filters(query, Widget, config, {"desc_search": "%"})
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 1
        assert results[0].name == "a"

    def test_ilike_escapes_underscore(self, widget_session, widget_factory):
        """ILIKE escapes _ wildcard so it matches literally."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        widget_factory(name="a", description="test_case passed")
        widget_factory(name="b", description="testXcase passed")

        config = [FilterField("description", FilterType.ILIKE, param_name="desc_search")]
        query = sa.select(Widget)
        filtered = apply_filters(query, Widget, config, {"desc_search": "test_case"})
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 1
        assert results[0].name == "a"

    @pytest.mark.skipif(True, reason="SQLite does not support backslash ESCAPE in LIKE")
    def test_ilike_escapes_backslash(self, widget_session, widget_factory):
        """ILIKE escapes backslash so it matches literally (PostgreSQL only)."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        widget_factory(name="a", description="C:\\Users\\test")
        widget_factory(name="b", description="CXUsersXtest")

        config = [FilterField("description", FilterType.ILIKE, param_name="desc_search")]
        query = sa.select(Widget)
        filtered = apply_filters(query, Widget, config, {"desc_search": "C\\Users"})
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 1
        assert results[0].name == "a"

    def test_ilike_none_skipped(self, widget_session, widget_factory):
        """None value for ILIKE filter is ignored."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        widget_factory(name="a", description="test")
        widget_factory(name="b", description="other")

        config = [FilterField("description", FilterType.ILIKE, param_name="desc_search")]
        query = sa.select(Widget)
        filtered = apply_filters(query, Widget, config, {"desc_search": None})
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 2


class TestApplyFiltersDateRange:
    """DATE_RANGE filter type tests."""

    def test_date_range_after(self, widget_session, widget_factory):
        """DATE_RANGE with _after key filters >= cutoff."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        old = datetime(2024, 1, 1, tzinfo=timezone.utc)
        new = datetime(2024, 6, 1, tzinfo=timezone.utc)
        cutoff = datetime(2024, 3, 1, tzinfo=timezone.utc)

        widget_factory(name="old", create_at=old)
        widget_factory(name="new", create_at=new)

        config = [FilterField("create_at", FilterType.DATE_RANGE)]
        query = sa.select(Widget)
        filtered = apply_filters(
            query, Widget, config, {"create_at_after": cutoff, "create_at_before": None}
        )
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 1
        assert results[0].name == "new"

    def test_date_range_before(self, widget_session, widget_factory):
        """DATE_RANGE with _before key filters <= cutoff."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        old = datetime(2024, 1, 1, tzinfo=timezone.utc)
        new = datetime(2024, 6, 1, tzinfo=timezone.utc)
        cutoff = datetime(2024, 3, 1, tzinfo=timezone.utc)

        widget_factory(name="old", create_at=old)
        widget_factory(name="new", create_at=new)

        config = [FilterField("create_at", FilterType.DATE_RANGE)]
        query = sa.select(Widget)
        filtered = apply_filters(
            query, Widget, config, {"create_at_after": None, "create_at_before": cutoff}
        )
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 1
        assert results[0].name == "old"

    def test_date_range_both_bounds(self, widget_session, widget_factory):
        """DATE_RANGE with both _after and _before narrows to range."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        early = datetime(2024, 1, 1, tzinfo=timezone.utc)
        middle = datetime(2024, 6, 1, tzinfo=timezone.utc)
        late = datetime(2024, 12, 1, tzinfo=timezone.utc)

        widget_factory(name="early", create_at=early)
        widget_factory(name="middle", create_at=middle)
        widget_factory(name="late", create_at=late)

        config = [FilterField("create_at", FilterType.DATE_RANGE)]
        query = sa.select(Widget)
        after = datetime(2024, 3, 1, tzinfo=timezone.utc)
        before = datetime(2024, 9, 1, tzinfo=timezone.utc)
        filtered = apply_filters(
            query, Widget, config, {"create_at_after": after, "create_at_before": before}
        )
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 1
        assert results[0].name == "middle"

    def test_date_range_none_both_skipped(self, widget_session, widget_factory):
        """None values for both DATE_RANGE keys are ignored."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        widget_factory(name="a", create_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
        widget_factory(name="b", create_at=datetime(2024, 6, 1, tzinfo=timezone.utc))

        config = [FilterField("create_at", FilterType.DATE_RANGE)]
        query = sa.select(Widget)
        filtered = apply_filters(
            query, Widget, config, {"create_at_after": None, "create_at_before": None}
        )
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 2


class TestApplyFiltersCombined:
    """Test multiple filter types combined."""

    def test_combined_exact_and_ilike(self, widget_session, widget_factory):
        """Multiple filter types combine with AND logic."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        widget_factory(name="alpha", active=True, description="error found")
        widget_factory(name="alpha", active=False, description="error found")
        widget_factory(name="beta", active=True, description="error found")
        widget_factory(name="alpha", active=True, description="success")

        config = [
            FilterField("name", FilterType.EXACT),
            FilterField("active", FilterType.EXACT, python_type=bool),
            FilterField("description", FilterType.ILIKE, param_name="desc_search"),
        ]
        query = sa.select(Widget)
        filtered = apply_filters(
            query,
            Widget,
            config,
            {"name": "alpha", "active": True, "desc_search": "error"},
        )
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 1
        assert results[0].name == "alpha"
        assert results[0].active is True

    def test_combined_exact_and_date_range(self, widget_session, widget_factory):
        """EXACT + DATE_RANGE filters work together."""
        from jm_api.api.generic.filters import FilterField, FilterType, apply_filters

        old = datetime(2024, 1, 1, tzinfo=timezone.utc)
        new = datetime(2024, 6, 1, tzinfo=timezone.utc)
        cutoff = datetime(2024, 3, 1, tzinfo=timezone.utc)

        widget_factory(name="alpha", create_at=old)
        widget_factory(name="alpha", create_at=new)
        widget_factory(name="beta", create_at=new)

        config = [
            FilterField("name", FilterType.EXACT),
            FilterField("create_at", FilterType.DATE_RANGE),
        ]
        query = sa.select(Widget)
        filtered = apply_filters(
            query,
            Widget,
            config,
            {"name": "alpha", "create_at_after": cutoff, "create_at_before": None},
        )
        results = widget_session.execute(filtered).scalars().all()
        assert len(results) == 1
        assert results[0].name == "alpha"


class TestMakeFilterDependency:
    """Test make_filter_dependency produces valid FastAPI dependency classes."""

    def test_dependency_has_expected_fields(self):
        """Generated dependency class has fields matching filter config."""
        from jm_api.api.generic.filters import FilterField, FilterType, make_filter_dependency

        config = [
            FilterField("name", FilterType.EXACT),
            FilterField("active", FilterType.EXACT, python_type=bool),
            FilterField("description", FilterType.ILIKE, param_name="desc_search"),
            FilterField("create_at", FilterType.DATE_RANGE),
        ]
        dep_cls = make_filter_dependency(config)

        # Should be instantiable with defaults (all None)
        instance = dep_cls()
        assert instance.name is None
        assert instance.active is None
        assert instance.desc_search is None
        assert instance.create_at_after is None
        assert instance.create_at_before is None

    def test_dependency_accepts_values(self):
        """Generated dependency class accepts values for fields."""
        from jm_api.api.generic.filters import FilterField, FilterType, make_filter_dependency

        config = [
            FilterField("name", FilterType.EXACT),
            FilterField("active", FilterType.EXACT, python_type=bool),
        ]
        dep_cls = make_filter_dependency(config)

        instance = dep_cls(name="test", active=True)
        assert instance.name == "test"
        assert instance.active is True

    def test_param_name_override(self):
        """FilterField with custom param_name uses that name in dependency."""
        from jm_api.api.generic.filters import FilterField, FilterType, make_filter_dependency

        config = [
            FilterField("last_run_log", FilterType.ILIKE, param_name="log_search"),
        ]
        dep_cls = make_filter_dependency(config)

        instance = dep_cls(log_search="test")
        assert instance.log_search == "test"
        # Should NOT have column_name as attribute
        assert not hasattr(instance, "last_run_log")
