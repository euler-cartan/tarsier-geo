"""Run one quality check and cache it (TAD §8  -  on demand, never on page load)."""

from tarsier.timing import timed_run, timed_phase
from tarsier.connectors.base import ConnectorError
from tarsier.connectors.registry import get_connector
from tarsier.quality.engine import (
    GEOMETRY_CHECKS,
    applicable_checks,
    check_boundary,
    check_completeness,
    check_custom_rules,
    check_dangles,
    check_gaps,
    check_overlaps,
    check_projection,
    check_slivers,
    check_validity,
    majority_srid,
    geometry_check_applicability,
)
from tarsier.limits import FULL_SCAN_MAX_ROWS
from tarsier.storage import connections as connection_storage
from tarsier.storage import quality_cache

DEFAULT_SAMPLE_LIMIT = 1000
# A "full" run is bounded too (tarsier.limits): a larger layer is checked on
# its first FULL_RUN_LIMIT rows and the result is labelled as a sample.
FULL_RUN_LIMIT = FULL_SCAN_MAX_ROWS


@timed_phase("fetch")
def _load_context(connection_id: str, schema: str, name: str):
    saved = connection_storage.get_connection(connection_id)
    if saved is None:
        raise ValueError(f"No such connection: {connection_id!r}")
    password = connection_storage.get_connection_password(connection_id)
    connector = get_connector(saved.type)
    config = connector.build_config(saved.config, password)
    if not hasattr(connector, "list_items"):
        raise ConnectorError(f"Quality checks aren't available yet for {saved.type} connections.")
    items = connector.list_items(config)
    item = next((i for i in items if i.schema == schema and i.name == name), None)
    if item is None:
        raise ConnectorError(f"{name!r} was not found on this connection  -  try running a check first.")
    if not item.readable:
        raise ConnectorError("No permission to read this table.")
    return saved, connector, config, items, item


def _limit(full: bool) -> int:
    return FULL_RUN_LIMIT if full else DEFAULT_SAMPLE_LIMIT


def _sample_geoms(connector, config, item, full: bool):
    if not hasattr(connector, "sample_geometries"):
        raise ConnectorError("Geometry quality checks aren't available yet for this connection type.")
    return connector.sample_geometries(config, item, limit=_limit(full))


@timed_run("quality")
def scan_check(connection_id: str, schema: str, name: str, check_id: str, *, full: bool = False):
    # A ruleless check needs only local state: do not discover the source or
    # evaluate unrelated alerts/automations, which can themselves read the source.
    if check_id == "custom_rules" and not quality_cache.list_rules(connection_id, schema, name):
        if connection_storage.get_connection(connection_id) is None:
            raise ValueError(f"No such connection: {connection_id!r}")
        result = check_custom_rules(None, [])
        quality_cache.save_check(connection_id, schema, name, result)
        return result
    saved, connector, config, items, item = _load_context(connection_id, schema, name)
    allowed = applicable_checks(item.kind)
    if check_id not in allowed:
        raise ConnectorError(f"{check_id} isn't applicable to {item.kind} items.")

    inapplicable = geometry_check_applicability(check_id, getattr(item, "geometry_type", None))
    if inapplicable is not None:
        quality_cache.save_check(connection_id, schema, name, inapplicable)
        return inapplicable

    if check_id == "completeness":
        if not hasattr(connector, "sample_id_values"):
            raise ConnectorError(f"Completeness isn't available yet for {saved.type} connections.")
        import inspect
        if "full" in inspect.signature(connector.sample_id_values).parameters:
            sample = connector.sample_id_values(config, item, full=full)
        else:
            sample = connector.sample_id_values(config, item)
        result = check_completeness(
            None if sample is None else sample.values,
            None if sample is None else sample.column,
            is_sample=bool(sample is not None and sample.is_sample),
        )
    elif check_id == "projection":
        result = check_projection(item.srid, majority_srid([i.srid for i in items]))
    elif check_id == "boundary":
        settings = quality_cache.get_settings(connection_id, schema, name)
        if settings is None or not settings.boundary_name:
            result = check_boundary(None, None)
        else:
            boundary_item = next(
                (
                    i
                    for i in items
                    if i.schema == settings.boundary_schema and i.name == settings.boundary_name
                ),
                None,
            )
            if boundary_item is None or boundary_item.kind != "vector":
                raise ConnectorError("The chosen boundary layer wasn't found, or isn't a vector layer.")
            target = _sample_geoms(connector, config, item, full)
            boundary = _sample_geoms(connector, config, boundary_item, True)
            result = check_boundary(target.geodataframe, boundary.geodataframe, is_sample=target.is_sample)
    elif check_id == "custom_rules":
        rules = quality_cache.list_rules(connection_id, schema, name)
        from tarsier.quality.engine import NEW_RULE_OPERATORS
        extended = [r for r in rules if r.get("operator") in NEW_RULE_OPERATORS]
        custom_limit = _limit(full)
        if extended:
            from tarsier.quality.rule_validation import columns_for, validate
            columns = columns_for(connection_id, schema, name)
            for rule in extended: validate(rule, columns)
            # Even an explicit full request remains a labelled sample above
            # one million rows. Connector queries retain their lock/time caps.
            custom_limit = min(custom_limit, FULL_SCAN_MAX_ROWS)
        if item.kind == "vector":
            sample = connector.sample_geometries(config, item, limit=custom_limit)
            result = check_custom_rules(sample.geodataframe, rules, is_sample=sample.is_sample)
        else:
            if not hasattr(connector, "sample_rows"):
                raise ConnectorError(f"Custom rules aren't available yet for {saved.type} connections.")
            sample = connector.sample_rows(config, item, limit=custom_limit)
            result = check_custom_rules(sample.dataframe, rules, is_sample=sample.is_sample)
    elif check_id in GEOMETRY_CHECKS:
        sample = _sample_geoms(connector, config, item, full)
        runners = {
            "validity": check_validity,
            "overlaps": check_overlaps,
            "slivers": check_slivers,
            "gaps": check_gaps,
            "dangles": check_dangles,
        }
        result = runners[check_id](sample.geodataframe, is_sample=sample.is_sample)
    else:
        raise ConnectorError(f"Unknown check: {check_id}")

    from dataclasses import replace
    details = getattr(locals().get("sample", locals().get("target")), "details", {})
    result = replace(result, sample_details=details)
    quality_cache.save_check(connection_id, schema, name, result)
    try:
        from tarsier.alerts.evaluate import evaluate_connection

        evaluate_connection(connection_id)
    except Exception:
        pass
    try:
        from tarsier.automation.evaluate import evaluate_connection as evaluate_autos

        evaluate_autos(connection_id)
    except Exception:
        pass
    return result
