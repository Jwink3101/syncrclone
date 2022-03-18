#!/usr/bin/env python
from __future__ import unicode_literals

__version__ = "20211010.0"
__author__ = "Justin Winokur"

import copy
from collections import defaultdict
import uuid
import types
import sys

if sys.version_info[0] > 2:
    unicode = str


class ExcludedAttributeError(ValueError):
    pass


class DictTable(object):
    """
    DictTable:
    Create an in-memeory single table DB from a list of dictionaries that may 
    be queried by any specified attribute.

    This is useful since, once created, lookup/query/"in" checks are O(1), 
    Creation is still O(N)

    Note: Unless an entry is changed with update(), it must be reindexed!

    Inputs:
    --------
    items  [ *empty* ] (list)
        Iterable of dictionaries with each attribute. Can also be a DictTable.
        If specified as a DictTable, other options are still settable here.

    fixed_attributes [None] (list, None)
        Specify _specific_ attributes to index for each item. Will *only* index
        them unless add_fixed_attribute('new_attribute') is called.
        
        If None, will use _all_ attributes *except* those of exclude_attributes
        
    exclude_attributes [ *empty* ] (list)
        Attributes that shouldn't ever be added even if attributes=None for 
        dynamic addition of attributes.
        
    Multiple Values per attribute
    -----------------------------
    A "row" can have multiple values per attribute as follows:
        
        {'attribute':[val1,val2,val3]}
        
    and can be queried for any (or all) values.
    
    Additional Opperations:
    ----------------------
    This supports index-lookup with a dictionary as well as
    a python `in` check and lookup by a dictionary
    
    The code will allow you to edit/delete/update multiple items at once
    (just like a standard database). Use with caution.

    Tips:
    ------
    * You can simply dump the DB with JSON using the DB.items()
      and then reload it with a new DB
    
    * There is also an attribute called `_index` which can be used to
      query by index.

    """

    def __init__(self, items=None, fixed_attributes=None, exclude_attributes=None):

        # These are used to make sure the DB.Query is (a) from this DB and (b)
        # the DB hasn't changed. This *should* always be the case
        self._id = unicode(uuid.uuid4())
        self._c = 0

        # Handle inputs
        if items is None:
            items = list()

        if exclude_attributes is None:
            exclude_attributes = set()
        if isinstance(exclude_attributes, (str, unicode)):
            exclude_attributes = [exclude_attributes]
        self.exclude_attributes = set(exclude_attributes)

        if fixed_attributes:
            if isinstance(fixed_attributes, (str, unicode)):
                fixed_attributes = [fixed_attributes]
            self.fixed_attributes = list(fixed_attributes)
        else:
            self.fixed_attributes = list()

        self.N = 0  # Will keep track
        self._list = []
        self._lookup = defaultdict(_new_defaultdict_list)

        self._empty = _emptyList()
        self._ix = set()

        # Add the items
        for item in items:
            self.add(item)

    def add(self, item):
        """
        Add an item or items to the DB
        """
        if isinstance(item, (list, tuple, types.GeneratorType)):
            for it in item:
                self.add(it)
            return

        ix = len(self._list)  # The length will be 1+ the last ix so do not change this

        # Add built in ones if it is there
        attribs = self.fixed_attributes if self.fixed_attributes else item.keys()

        for attrib in attribs:
            if attrib not in item or attrib in self.exclude_attributes:
                continue
            self._append(attrib, item[attrib], ix)  # Add it to the index

        # Finally add it
        self._list.append(item)
        self.N += 1
        self._ix.add(ix)

    def query(self, *args, **kwargs):
        """
        Query the value for attribute. Will always an iterator. Use
        `list(DB.query())` to return a list
        
        Usage
        -----
        
        Any combination of the following will works
        
        Keywords: Only check equality
                   
        >>> DB.query(attrib=val)
        >>> DB.query(attrib1=val1,attrib2=val2)  # Match both
        
        >>> DB.query({'attrib':val})
        >>> DB.query({'attrib1':val1,'attrib2':val2}) # Match Both
                                      
        Query Objects (DB.Q, DB.Query)
        
        >>> DB.query(DB.Q.attrib == val)
        >>> DB.query( (DB.Q.attrib1 == val1) &  (DB.Q.attrib1 == val2) )  # Parentheses are important!
        >>> DB.query( (DB.Q.attrib1 == val1) &  (DB.Q.attrib1 != val2) )
                                   
        """
        ixs = self._ixs(*args, **kwargs)
        for ix in ixs:
            yield self._list[ix]

    def query_one(self, *args, **kwargs):
        """
        Return a single item from a query. See "query" for more details.
        
        Returns None if nothing matches
        """
        try:
            return next(self.query(*args, **kwargs))
        except StopIteration:
            return None

    def pop(self, *args, **kwargs):
        """
        Query, delete, and return item.
        
        Will raise a ValueError if more than one item will be deleted 
        Will raise a KeyError if there is no item to delete. Does *NOT* support a default
        """
        ixs = self._ixs(*args, **kwargs)
        if len(ixs) == 0:
            raise KeyError("No matching query")
        if len(ixs) > 1:
            raise ValueError("Cannot `.pop()` more than one item`")
        ix = ixs[0]
        item = self._list[ix]
        self._remove_ix(ix)
        return item

    def count(self, *args, **kwargs):
        """
        Return the number of matched rows for a given query. See "query" for
        details on query construction
        """
        return len(self._ixs(*args, **kwargs))

    def isin(self, *args, **kwargs):
        """
        Check if there is at least one item that matches the given query
        
        see query() for usage
        """
        return self.count(*args, **kwargs) > 0

    def reindex(self, *attributes):
        """
        Reindex the dictionary for specified attributes (or all)
        
        Usage
        -----
        
        >>> DB.reindex()                # All
        >>> DB.reindex('attrib')        # Reindex 'attrib'
        >>> DB.reindex('attrib1','attrib2') # Multiple
        
        See Also
        --------
            update() method which does not require reindexing
        """
        if len(attributes) == 0:
            attributes = self.attributes

        if any(a in self.exclude_attributes for a in attributes):
            raise ValueError("Cannot reindex an excluded attribute")

        for attribute in attributes:
            self._lookup[attribute] = defaultdict(list)  # Reset

        for ix, item in enumerate(self._list):
            if item is None:
                continue
            for attrib in attributes:
                if attrib in item:
                    self._append(attrib, item[attrib], ix)

    def update(self, *args, **queryKWs):
        """
        Update an entry without needing to reindex the DB (or a specific
        attribute)
        
        Usage:
        ------
        
        >>> DB.update(updated_dict, query_dict_or_Query, query_attrib1=val1,...)
        >>> DB.update(updated_dict, query_attrib1=val1,...)
        
        Inputs:
        -------
        
        updated_dict : Dictionary with which to update the entry. This is
                       done using the typical dict().update() construct to
                       overwrite it
        
        query_dict_or_Query
                     : Either the dictionary used in the query or a Query that
                       defines a more advanced query
        
        query_attrib1=val1
                     : Additional (or sole) query attributes
    
        Notes:
        ------
            * Updating an item requires a deletion in a list that has length n
              equal to the number of items matching an attribute. This is O(n).
              However changing the entry directly and reindexing is O(N) where
              N is the size of the DB. If many items are changing and you do not
              need to query them in between, it *may* be faster to directly
              update the item and reindex
        """

        if len(args) == 1:
            updated_dict = args[0]
            query = {}
        elif len(args) == 2:
            updated_dict, query = args
        else:
            raise ValueError("Incorrect number of inputs. See documentation")

        if not isinstance(updated_dict, dict):
            raise ValueError("Must specify updated values as a dictionary")

        if isinstance(query, Query):
            ixs = self._ixs(query, **queryKWs)
        elif isinstance(query, dict):
            queryKWs.update(query)
            ixs = self._ixs(**queryKWs)
        else:
            raise ValueError(
                "Unrecognized query {:s}. Must be a dict or Query", format(type(query))
            )

        if len(ixs) == 0:
            raise ValueError("Query did not match any results")

        for ix in ixs:
            # Get original item
            item = self._list[ix]

            # Allow the update to also include non DB attributes.
            # The intersection will eliminate any exclude_attributes
            attributes = set(updated_dict.keys()).intersection(self.attributes)

            for attrib in attributes:  # Only loop over the updated attribs
                value = item[attrib]  # get old value
                self._remove(attrib, value, ix)  # Remove any ix matching it
                value = updated_dict[attrib]  # Get new value
                self._append(attrib, value, ix)  # Add ix to any new value

            item.update(updated_dict)  # Update the item

    def add_fixed_attribute(self, attrib, force=False):
        """
        Adds a fixed attribute. If there are NO fixed attributes (i.e. it is
        dynamic attributes), do *NOT* add them unless force.
        
        Will reindex either way
        """
        if attrib in self.exclude_attributes:
            raise ExcludedAttributeError("'{}' is excludes".format(attrib))

        if (
            self.fixed_attributes or force and attrib not in self.fixed_attributes
        ):  # Must already be filled or forced
            self.fixed_attributes.append(attrib)

        self.reindex(attrib)

    def remove(self, *args, **kwargs):
        """
        Remove item that matches a given attribute or dict. See query() for
        input specification
        -----------
        """
        ixs = list(self._ixs(*args, **kwargs))

        if len(ixs) == 0:
            raise ValueError("No matching items")

        items = []

        for ix in ixs[:]:  # Must remove it from everything.
            # not sure what is happening, but it seems that I need to make a copy
            # since Python is doing something strange here...
            self._remove_ix(ix)

    def _remove_ix(self, ix):
        item = self._list[ix]
        for attrib in self.attributes:
            if attrib in item:
                self._remove(attrib, item[attrib], ix)

        # Remove it from the list by setting to None. Do not reshuffle
        # the indices. A None check will be performed elsewhere
        self._list[ix] = None
        self._ix.difference_update([ix])
        self.N -= 1

    def copy(self):
        return DictTable(
            self,
            exclude_attributes=copy.copy(self.exclude_attributes),
            fixed_attributes=copy.copy(self.fixed_attributes),
        )

    __copy__ = copy

    @property
    def Query(self):
        """
        Query object already loaded with the DB
        
            DB.Query <==> DB.Q
        """
        return Query(self)

    Q = Query

    def _ixs(self, *args, **kwargs):
        """
        Get the inde(x/ies) of matching information
        """
        if not hasattr(self, "_lookup") or self.N == 0:  # It may be empty
            return []

        # Make the entire kwargs be lists with default of []. Edge case of
        # multiple items
        for key, val in kwargs.items():
            if not isinstance(val, list):
                kwargs[key] = [val]
        kwargs = defaultdict(list, kwargs)

        Q = Query(self)  # Empty object
        for arg in args:
            if isinstance(arg, Query):
                if arg._id != self._id:
                    raise ValueError("Cannot use another DictTable's Query object")

                Q = (
                    Q & arg
                )  # Will add these conditions. If Q is empty, will just be arg
                continue
            if isinstance(arg, dict):
                for (
                    key,
                    val,
                ) in (
                    arg.items()
                ):  # Add it rather than update in case it is already specified
                    kwargs[key].append(
                        val
                        if not (isinstance(val, list) and len(val) == 0)
                        else self._empty
                    )
            else:
                raise ValueError(
                    "unrecognized input of type {:s}".format(str(type(arg)))
                )

        # Construct a query for kwargs
        for key, value in kwargs.items():
            if isinstance(value, list) and len(value) == 0:
                value = [self._empty]
            for val in _makelist(value):
                Qtmp = Query(self)
                Qtmp._attr = key
                Q = Q & (Qtmp == val)

        ixs = Q._ixs
        return list(ixs)

    def _index(self, ix):
        """
        Return ix if it hasn't been deleted
        """
        try:
            item = self._list[ix]
        except IndexError:
            return []

        if item is None:
            return []
        return [ix]

    def _append(self, attrib, value, ix):
        """
        Add to the lookup and update the modify time
        """
        # Final check but we should be guarded from this
        if attrib in self.exclude_attributes:
            # print('BAD! Should guard against this in public methods!')
            raise ValueError("Cannot reindex an excluded attribute")

        valueL = _makelist(value)
        for val in valueL:
            self._lookup[attrib][val].append(ix)
        if len(valueL) == 0:
            self._lookup[attrib][self._empty].append(ix)  # empty list

        self._c += 1

    def _remove(self, attrib, value, ix):
        """
        Remove from the lookup and update the modify time
        """
        valueL = _makelist(value)
        for val in valueL:
            try:
                self._lookup[attrib][val].remove(ix)
            except ValueError:
                raise ValueError(
                    "Item not found in internal lookup. May need to first call reindex()"
                )
        if len(valueL) == 0:
            self._lookup[attrib][self._empty].remove(ix)  # empty list

        self._c += 1

    def __contains__(self, check_diff):
        if not (isinstance(check_diff, dict) or isinstance(check_diff, Query)):
            raise ValueError(
                "Python `in` queries should be a of {attribute:value} or Query"
            )
        return self.isin(check_diff)

    def __len__(self):
        return self.N

    def __getitem__(self, item):
        if isinstance(item, dict) or isinstance(item, Query):
            return self.query_one(item)
        elif isinstance(item, int):  # numbered item
            if self._list[item] is not None:
                return self._list[item]
            else:
                raise ValueError("Index has been deleted")
        else:
            raise ValueError("Must specify DB[{'attribute':val}] or DB[index]'")

    __call__ = query
    __delitem__ = remove

    def __iter__(self):
        return (item for item in self._list if item is not None)

    items = __iter__

    @property
    def attributes(self):
        # The attributes are the keys of _lookup but _lookup is a defaultdict
        # of a defaultdict(list) so need to check that it is also empy
        if self.fixed_attributes:
            return self.fixed_attributes

        attribs = []
        # This seems slow but the second for-loop will break at the first non-empty
        # item (likely the first one)
        for attrib, val in self._lookup.items():
            if not val:  # Empty
                continue
            for v in val.values():
                if v:
                    break
            else:
                continue

            attribs.append(attrib)
        attribs.sort()
        return attribs


def _makelist(input):
    if isinstance(input, list):
        return input
    return [input]


class _emptyList(object):
    def __init__(self):
        pass

    def __hash__(self):
        return 9999999999999

    def __eq__(self, other):
        return isinstance(other, list) and len(other) == 0


def _new_defaultdict_list():
    return defaultdict(list)


class Query(object):
    """
    Query objects. This works by returning an updated *copy* of the object
    whenever it is acted upon
    
    Calling
        * Q.attribute sets attribute and returns a copy
        * Q.attribute == val (or any other comparison) set the index of elements
        * Q1 & Q1 or other boolean perform set operations
        
    Useful Methods:
        _filter : (or just `filter` if not an attribute): Apply a filter
                  to the DB
    """

    def __init__(self, DB):
        self._DB = DB
        self._ixs = DB._ix  # Everything. Do *NOT* copy but also never modify in place
        self._attr = None

        self._c = DB._c
        self._id = DB._id

    def _valid(self):
        if self._c != self._DB._c:
            raise ValueError(
                "This query object is out of date from the DB. Create a new one"
            )

    def _filter(self, filter_func):
        """
        If 'filter' is NOT an attribute of the DB, this can be called
        with 'filter' instead of '_filter'
        
        Apply a filter to the data that returns True if it matches and False
        otherwise
        
        Note that filters are O(N)
        """
        self._valid()  # Actually, these would still work but still check
        ixs = set()
        for ix, item in enumerate(self._DB._list):  # loop all
            if item is None:
                continue
            if filter_func(item):
                ixs.add(ix)
        self._ixs = ixs  # reset it
        return self

    # Comparisons
    def __eq__(self, value):
        self._valid()

        if not self._ixs:
            return self

        # Account for '_index' attribute (May be deprecated in the future...)
        if self._attr == "_index":
            self._ixs = self._ixs.intersection({value})  # replace, don't update
            return self
        for val in _makelist(value):
            self._ixs = self._ixs.intersection(
                self._DB._lookup[self._attr][val]
            )  # Will return [] if _attr or val not there . Replace, don't update
        return self

    def __ne__(self, value):
        self._ixs = self._DB._ix - (self == value)._ixs
        return self

    def __lt__(self, value):
        self._valid()  # Actually, these would still work but still check
        ixs = set()
        for ix, item in enumerate(self._DB._list):  # loop all
            if item is None or self._attr not in item:
                continue
            for ival in _makelist(item[self._attr]):
                if ival < value:
                    ixs.add(ix)
        self._ixs = ixs
        return self

    def __le__(self, value):
        self._valid()  # Actually, these would still work but still check
        ixs = set()
        for ix, item in enumerate(self._DB._list):  # loop all
            if item is None:
                continue
            if self._attr in item and item[self._attr] <= value:
                ixs.add(ix)
        self._ixs = ixs
        return self

    def __gt__(self, value):
        self._valid()  # Actually, these would still work but still check
        ixs = set()
        for ix, item in enumerate(self._DB._list):  # loop all
            if item is None:
                continue
            if self._attr in item and item[self._attr] > value:
                ixs.add(ix)
        self._ixs = ixs
        return self

    def __ge__(self, value):
        self._valid()  # Actually, these would still work but still check
        ixs = set()
        for ix, item in enumerate(self._DB._list):  # loop all
            if item is None:
                continue
            if self._attr in item and item[self._attr] >= value:
                ixs.add(ix)
        self._ixs = ixs
        return self

    # Logic
    def __and__(self, Q2):
        self._ixs = self._ixs.intersection(Q2._ixs)
        return self

    def __or__(self, Q2):
        self._ixs = self._ixs.union(Q2._ixs)
        return self

    def __invert__(self):
        self._ixs = self._DB._ix - self._ixs
        return self

    # Attributes
    def __getattr__(self, attr):
        if self._attr is not None:
            raise ValueError("Already set attribute")
        if attr == "filter" and "filter" not in self._DB.attributes:
            return self._filter

        self._attr = attr
        if attr == "_index":
            return self

        ixs = set()
        for vals in self._DB._lookup[attr].values():
            ixs.update(vals)
        self._ixs = ixs
        return self
