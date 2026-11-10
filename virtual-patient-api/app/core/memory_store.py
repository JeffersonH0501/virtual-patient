"""Segment-safe namespace queries for the qualified PostgresStore 2.0.23 API."""
import re
from importlib.metadata import version

from langgraph.store.base import GetOp, ListNamespacesOp, PutOp, SearchOp
from langgraph.store.postgres import PostgresStore as _PostgresStore
from app.core.async_work import run_sync_owned


if version('langgraph-checkpoint-postgres') != '2.0.23':
    raise RuntimeError('Requalify the memory namespace adapter before changing PostgresStore')


def _pattern(path, *, suffix=False, wildcards=False):
    parts = ['[^.]+' if wildcards and label == '*' else re.escape(label) for label in path]
    body = '[.]'.join(parts)
    return '(^|[.])' + body + '$' if suffix else '^' + body + '([.]|$)'


class PostgresStore(_PostgresStore):
    """Keep upstream storage/ranking; restrict namespace matches in SQL before top-k."""

    async def abatch(self, ops):
        return await run_sync_owned(self.batch, ops)

    def batch(self, ops):
        ops = list(ops)
        for op in ops:
            if isinstance(op, (GetOp, PutOp)):
                paths = [op.namespace]
            elif isinstance(op, SearchOp):
                paths = [op.namespace_prefix]
            elif isinstance(op, ListNamespacesOp):
                paths = [condition.path for condition in op.match_conditions or ()]
            else:
                raise ValueError('Unsupported memory store operation')
            for path in paths:
                if not isinstance(path, tuple):
                    raise ValueError('Namespaces must be tuples of labels')
                if any(not isinstance(label, str) or not label or '.' in label for label in path):
                    raise ValueError('Namespace labels must be nonempty strings without dots')
        return super().batch(ops)

    def _prepare_batch_search_queries(self, search_ops):
        queries, embeddings = super()._prepare_batch_search_queries(search_ops)
        for index, (_, op) in enumerate(search_ops):
            if not op.namespace_prefix:
                continue
            query, params = queries[index]
            if query.count('store.prefix LIKE %s') != 1:
                raise RuntimeError('Unexpected PostgresStore namespace query shape')
            params = list(params)
            params[1 if op.query and self.index_config else 0] = _pattern(op.namespace_prefix)
            queries[index] = (query.replace('store.prefix LIKE %s', 'store.prefix ~ %s'), params)
        return queries, embeddings

    def _get_batch_list_namespaces_queries(self, list_ops):
        queries = super()._get_batch_list_namespaces_queries(list_ops)
        for index, (_, op) in enumerate(list_ops):
            query, params = queries[index]
            conditions = op.match_conditions or ()
            if query.count('prefix LIKE %s') != len(conditions):
                raise RuntimeError('Unexpected PostgresStore namespace listing query shape')
            params = list(params)
            for position, condition in enumerate(conditions, start=2):
                if condition.match_type not in ('prefix', 'suffix'):
                    raise ValueError('Unsupported namespace match type')
                params[position] = _pattern(condition.path, suffix=condition.match_type == 'suffix', wildcards=True)
            queries[index] = (query.replace('prefix LIKE %s', 'prefix ~ %s'), tuple(params))
        return queries
