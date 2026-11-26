"""Catalog validation for the three extended attribute-rule families."""
import re

from sqlalchemy import text

from tarsier.connectors.base import ConnectorError
from tarsier.quality.engine import NEW_RULE_OPERATORS, RULE_OPERATORS


def columns_for(connection_id, schema, name):
    from tarsier.quality.scan import _load_context
    saved, connector, config, _, item = _load_context(connection_id, schema, name)
    if saved.type == "postgis":
        from tarsier.connectors.postgis import _build_engine, _clean_connection_error
        from sqlalchemy.exc import OperationalError
        engine = _build_engine(config)
        try:
            with engine.connect() as conn:
                rows = conn.execute(text("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=:s AND table_name=:n AND udt_name NOT IN ('geometry','geography','raster')"), {"s":schema,"n":name}).all()
                return dict(rows)
        except OperationalError as exc:
            raise _clean_connection_error(config, exc) from exc
        finally:
            engine.dispose()
    sample = connector.sample_rows(config, item, limit=1)
    return {str(col):str(dtype) for col,dtype in sample.dataframe.dtypes.items() if col not in (sample.geometry_columns or ())}


def _family(kind):
    kind=kind.lower()
    if kind in ('smallint','integer','bigint','numeric','decimal','double precision','real') or re.fullmatch(r'(?:u?int|float)\d*',kind):return 'number'
    if kind in ('text','character varying','character','object','string','str'):return 'text'
    if 'timestamp' in kind or kind.startswith('datetime') or kind=='date':return 'date'
    if kind in ('boolean','bool'):return 'bool'
    return None


def validate(rule, columns):
    operator=rule.get('operator') or 'eq'
    if operator not in RULE_OPERATORS:
        raise ConnectorError('Unknown custom-rule operator.')
    if operator not in NEW_RULE_OPERATORS:return
    if rule.get('kind','attribute')!='attribute':
        raise ConnectorError('These operators apply to attribute rules only.')
    field=rule.get('field');value=rule.get('value')
    if field not in columns:
        raise ConnectorError('Pick a field from this table\'s catalog.')
    if operator.startswith('column_'):
        if value not in columns:
            raise ConnectorError('Pick another column from the same table.')
        left,right=_family(columns[field]),_family(columns[value])
        if left is None or left!=right or (left=='bool' and operator not in ('column_eq','column_ne')):
            raise ConnectorError('These columns do not have compatible types for this comparison.')
    if operator in ('matches','not_matches'):
        if _family(columns[field])!='text':raise ConnectorError('Text patterns require a text column.')
        if value is None:raise ConnectorError('Enter a regular expression.')
        try:re.compile(value)
        except (re.error,OverflowError) as exc:raise ConnectorError('Invalid regular expression. Check the text pattern.') from exc
    if operator=='is_unique' and value not in (None,''):
        raise ConnectorError('IS UNIQUE does not accept a value.')
