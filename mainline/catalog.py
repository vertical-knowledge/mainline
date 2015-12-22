import abc
import collections
import six

from mainline.provider import IProvider
from mainline.utils import ProxyMutableMapping, dedupe_iter

_sentinel = object()
_provider_mapping_factory = dict


class ProviderMapping(ProxyMutableMapping):
    '''
    Mixin to provide mapping interface on providers
    '''

    _mapping_factory = _provider_mapping_factory

    def __init__(self, *args, **kwargs):
        if self.__class__._providers:
            self._providers = self.__class__._providers.copy()
        else:
            self._providers = self._mapping_factory()
        super(ProviderMapping, self).__init__(self._providers)
        self.update(dict(*args, **kwargs))


class ICatalog(object):
    '''
    Inherit from this class to note that you support the ICatalog interface
    '''

    _providers = None


class CatalogMeta(abc.ABCMeta):
    '''
    Meta class used to populate providers from attributes of Catalog subclass declarations.
    '''

    _provider_mapping_factory = _provider_mapping_factory

    def __new__(mcs, class_name, bases, attributes):
        cls = super(CatalogMeta, mcs).__new__(mcs, class_name, bases, attributes)

        # We may already have providers. If so, make a copy.
        if cls._providers:
            cls._providers = cls._providers.copy()
        else:
            cls._providers = mcs._provider_mapping_factory()

        cls._providers.update(
            {k: v for k, v in six.iteritems(attributes)
             if isinstance(v, IProvider)}
        )

        return cls


@six.add_metaclass(CatalogMeta)
class Catalog(ICatalog, ProviderMapping):
    pass


class LayeredCatalog(ICatalog, collections.MutableMapping):
    """
    Provides a providers dictionary with the ability to add/remove catalogs.

    TODO Look into multiple heapqs for each key to keep track of who has what provider

    >>> lc = LayeredCatalog()
    >>> c = Catalog({'test': 'catalog_c'})
    >>> d = Catalog({'test': 'catalog_d'})
    >>> lc['test']
    Traceback (most recent call last):
    ...
    KeyError: 'test'
    >>> lc.catalogs.append(c)
    >>> lc['test']
    'catalog_c'
    >>> lc.catalogs.append(d)
    >>> lc['test']
    'catalog_c'
    >>> lc.catalogs.remove(c)
    >>> lc['test']
    'catalog_d'
    >>> lc.catalogs.append(c)
    >>> lc['test']
    'catalog_d'

    """

    def __init__(self):
        self.catalogs = []
        self.default = Catalog()
        self.override = Catalog()

    def insert(self, i, catalog):
        return self.catalogs.insert(i, catalog)

    def append(self, catalog):
        return self.catalogs.append(catalog)

    def remove(self, catalog):
        return self.catalogs.remove(catalog)

    @property
    def search_order(self):
        yield self.override
        for catalog in self.catalogs:
            yield catalog
        yield self.default

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, list(self.search_order))

    # def _ifilter(self, flt):
    #     return (catalog for catalog in self.search_order if flt(catalog))

    def _icontains(self, item):
        return (catalog for catalog in self.search_order if item in catalog)

    def __contains__(self, item):
        return bool(next(self._icontains(item), False))

    def __getitem__(self, item):
        for catalog in self._icontains(item):
            return catalog[item]
        return self.default[item]

    def __setitem__(self, key, value):
        catalog = next(self._icontains(key), self.default)
        catalog[key] = value

    def __delitem__(self, key):
        # TODO Marker for deleted instead of removing the actual item
        # set_instance(key, self._DELETED) in an override mapping or deleted items set etc, could also store the catalog provider to ensure only that one is marked as deleted. Or better yet just mark that provider as deleted. That's the best route.
        catalog = next(self._icontains(key), self.default)
        del catalog[key]

    def keys(self):
        gen = (key for catalog in self.search_order for key in catalog)
        return dedupe_iter(gen)

    def values(self):
        for key in self.keys():
            yield self[key]

    def items(self):
        for key in self.keys():
            yield key, self[key]

    __iter__ = keys

    def __len__(self):
        return len(self.keys())
