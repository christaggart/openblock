from django.contrib.gis.db import models
from django.contrib.gis.db.models import Count
from django.db.models import Q
from ebpub.streets.models import Block
from ebpub.utils.text import slugify
import datetime

# Need these monkeypatches for "natural key" support during fixture load/dump.
import ebpub.monkeypatches
ebpub.monkeypatches.patch_once()

FREQUENCY_CHOICES = ('Hourly', 'Throughout the day', 'Daily', 'Twice a week', 'Weekly', 'Twice a month', 'Monthly', 'Quarterly', 'Sporadically', 'No longer updated')
FREQUENCY_CHOICES = [(a, a) for a in FREQUENCY_CHOICES]

# backward compatibility: moved the old Attribute stuff
# to a new module, so we can mostly ignore it,
# but still use them so we can provide the populate_clones.py
# migration script.  (Might want to re-think that.)
from old_attribute_models import AttributesDescriptor


class SchemaManager(models.Manager):

    def get_by_natural_key(self, slug):
        return self.get(slug=slug)

    def get_query_set(self):
        return super(SchemaManager, self).get_query_set().defer(
            'short_description',
            'summary',
            'source',
            'grab_bag_headline',
            'grab_bag',
            'short_source',
            'update_frequency',
            'intro',
            )


class SchemaPublicManager(SchemaManager):

    def get_query_set(self):
        return super(SchemaManager, self).get_query_set().filter(is_public=True)

class Schema(models.Model):
    """
    Describes a type of NewsItem.  A NewsItem has exactly one Schema,
    which describes its attributes, via associated SchemaFields.

    nb. to get all NewsItem instances for a Schema, you can do the usual as per
    http://docs.djangoproject.com/en/dev/topics/db/queries/#backwards-related-objects:
    schema.newsitem_set.all()
    """
    name = models.CharField(max_length=32)
    plural_name = models.CharField(max_length=32)
    indefinite_article = models.CharField(max_length=2) # 'a' or 'an'
    slug = models.CharField(max_length=32, unique=True)
    min_date = models.DateField() # the earliest available NewsItem.pub_date for this Schema
    last_updated = models.DateField()
    date_name = models.CharField(max_length=32, default='Date') # human-readable name for the NewsItem.item_date field
    date_name_plural = models.CharField(max_length=32, default='Dates')
    importance = models.SmallIntegerField(default=0) # bigger number is more important
    is_public = models.BooleanField(db_index=True, default=False)
    is_special_report = models.BooleanField(default=False)

    # whether RSS feed should collapse many of these into one
    can_collapse = models.BooleanField(default=False)

    # whether a newsitem_detail page exists for NewsItems of this Schema
    has_newsitem_detail = models.BooleanField(default=False)

    # whether aggregate charts are allowed for this Schema
    allow_charting = models.BooleanField(default=False)

    # whether attributes should be preloaded for NewsItems of this
    # Schema, in the list view
    uses_attributes_in_list = models.BooleanField(default=False)

    # number of records to show on place_overview
    number_in_overview = models.SmallIntegerField(default=5)

    objects = SchemaManager()
    public_objects = SchemaPublicManager()

    def __unicode__(self):
        return self.name

    def natural_key(self):
        return (self.slug,)

    def url(self):
        return '/%s/' % self.slug

    def icon_slug(self):
        if self.is_special_report:
            return 'special-report'
        return self.slug


    # Metadata fields moved from SchemaInfo
    short_description = models.TextField(blank=True, default='')
    summary = models.TextField(blank=True, default='')
    source = models.TextField(blank=True, default='')
    grab_bag_headline = models.CharField(max_length=128, blank=True, default='')
    grab_bag = models.TextField(blank=True, default='')  # TODO: what does this field mean?
    short_source = models.CharField(max_length=128, blank=True, default='')
    update_frequency = models.CharField(max_length=64, blank=True, default='',
                                        choices=FREQUENCY_CHOICES)
    intro = models.TextField(blank=True, default='')


class SchemaFieldManager(models.Manager):

    def get_by_natural_key(self, schema_slug, real_name):
        return self.get(schema__slug=schema_slug, real_name=real_name)

class SchemaField(models.Model):
    """
    Describes the meaning of one Attribute field for one Schema type.
    """
    objects = SchemaFieldManager()

    schema = models.ForeignKey(Schema)
    name = models.CharField(max_length=32)
    real_name = models.CharField(max_length=10) # Column name in the Attribute model. 'varchar01', 'varchar02', etc.
    pretty_name = models.CharField(max_length=32) # human-readable name, for presentation
    pretty_name_plural = models.CharField(max_length=32) # plural human-readable name
    display = models.BooleanField(default=True) # whether to display value on the public site
    is_lookup = models.BooleanField(default=False) # whether the value is a foreign key to Lookup
    is_filter = models.BooleanField(default=False)  # whether to show links to all other NewsItems with this value.  Only valid when is_lookup=True.
    is_charted = models.BooleanField(default=False) # whether schema_detail displays a chart for this field; also see "trends" tabs on place_overview.html
    display_order = models.SmallIntegerField(default=10)
    is_searchable = models.BooleanField(default=False) # whether the value is searchable by content. Don't use on Lookup fields, only text or varchar.

    def natural_key(self):
        return (self.schema.slug, self.real_name)

    class Meta(object):
        unique_together = (('schema', 'real_name'),)

    def __unicode__(self):
        return u'%s - %s' % (self.schema, self.name)

    @property
    def slug(self):
        return self.name.replace('_', '-')

    @property
    def datatype(self):
        return self.real_name[:-2]

    def is_type(self, *data_types):
        """
        Returns True if this SchemaField is of *any* of the given data types.

        Allowed values are 'varchar', 'date', 'time', 'datetime', 'bool', 'int'.
        """
        return self.datatype in data_types

    def is_many_to_many_lookup(self):
        """
        Returns True if this SchemaField is a many-to-many lookup.
        """
        # XXX spikify - do we even need this? all lookups are potentially m2m
        return self.is_lookup and not self.is_type('int')

    def all_lookups(self):
        if not self.is_lookup:
            raise ValueError('SchemaField.all_lookups() can only be called if is_lookup is True')
        return Lookup.objects.filter(schema_field__id=self.id).order_by('name')

    def browse_by_title(self):
        "Returns FOO in 'Browse by FOO', for this SchemaField."
        if self.is_type('bool'):
            return u'whether they %s' % self.pretty_name_plural
        return self.pretty_name

    def smart_pretty_name(self):
        """
        Returns the pretty name for this SchemaField, taking into account
        many-to-many fields.
        """
        if self.is_many_to_many_lookup():
            return self.pretty_name_plural
        return self.pretty_name


class LocationTypeManager(models.Manager):
    def get_by_natural_key(self, slug):
        return self.get(slug=slug)

class LocationType(models.Model):
    name = models.CharField(max_length=255) # e.g., "Ward" or "Congressional District"
    plural_name = models.CharField(max_length=64) # e.g., "Wards"
    scope = models.CharField(max_length=64) # e.g., "Chicago" or "U.S.A."
    slug = models.CharField(max_length=32, unique=True)
    is_browsable = models.BooleanField() # whether this is displayed on location_type_list
    is_significant = models.BooleanField() # whether this is used to display aggregates, shows up in 'nearby locations', etc.

    def __unicode__(self):
        return u'%s, %s' % (self.name, self.scope)

    def url(self):
        return '/locations/%s/' % self.slug

    def natural_key(self):
        return (self.slug,)

    objects = LocationTypeManager()


class LocationManager(models.GeoManager):
    def get_by_natural_key(self, slug, location_type_slug):
        return self.get(slug=slug, location_type__slug=slug)

class Location(models.Model):
    name = models.CharField(max_length=255) # e.g., "35th Ward"
    normalized_name = models.CharField(max_length=255, db_index=True)
    slug = models.CharField(max_length=32, db_index=True)
    location_type = models.ForeignKey(LocationType)
    location = models.GeometryField(null=True)
    centroid = models.PointField(null=True)
    display_order = models.SmallIntegerField()
    city = models.CharField(max_length=255)
    source = models.CharField(max_length=64)
    area = models.FloatField(blank=True, null=True) # in square meters
    population = models.IntegerField(blank=True, null=True) # from the 2000 Census
    user_id = models.IntegerField(blank=True, null=True)
    is_public = models.BooleanField()
    description = models.TextField(blank=True)
    creation_date = models.DateTimeField(blank=True, null=True)
    last_mod_date = models.DateTimeField(blank=True, null=True)
    objects = LocationManager()

    class Meta:
        unique_together = (('slug', 'location_type'),)

    def natural_key(self):
        return (self.slug, self.location_type.slug)

    def __unicode__(self):
        return self.name

    def url(self):
        return '/locations/%s/%s/' % (self.location_type.slug, self.slug)

    def rss_url(self):
        return '/rss%s' % self.url()

    def alert_url(self):
        return '%salerts/' % self.url()

    def edit_url(self):
        return '/locations/%s/edit/%s/' % (self.location_type.slug, self.slug)

    # Give Location objects a "pretty_name" attribute for interoperability with
    # Block objects. (Parts of our app accept either a Block or Location.)
    @property
    def pretty_name(self):
        return self.name

    @property
    def is_custom(self):
        return self.location_type.slug == 'custom'



class NewsItemQuerySet(models.query.GeoQuerySet):

    def by_attribute(self, schema_field, att_value, is_lookup=False):
        """
        Returns a QuerySet of NewsItems whose attribute value for the given
        SchemaField is att_value. If att_value is a list, this will do the
        equivalent of an "OR" search, returning all NewsItems that have an
        attribute value in the att_value list.

        Note that this necessarily implies you've already filtered by
        one specific Schema, and have instances of a corresponding
        NewsItem subclass.  This is best accomplished via
        NewsItem.objects_by_schema(schema).

        This handles many-to-many lookups correctly behind the scenes.

        If is_lookup is True, then att_value is treated as the 'code' of a
        Lookup object, and the Lookup's ID will be retrieved for use in the
        query.
        """
        # XXX TODO: since we now have attributes on subclasses,
        # maybe just replace this with the normal filter API?
        clone = self._clone()

        if not isinstance(att_value, (list, tuple)):
            att_value = [att_value]
        if is_lookup:
            att_value = Lookup.objects.filter(schema_field__id=schema_field.id, code__in=att_value)
            if not att_value:
                # If the lookup values don't exist, then there aren't any
                # NewsItems with this attribute value. Note that we aren't
                # using QuerySet.none() here, because we want the result to
                # be a NewsItemQuerySet, and none() returns a normal QuerySet.
                clone = clone.extra(where=('1=0',))
                return clone
            att_value = [val.id for val in att_value]
        if schema_field.is_lookup: #many_to_many_lookup():
            lookup_args = {schema_field.slug + '__in': att_value}
            clone = clone.filter(**lookup_args)
        elif None in att_value:
            if att_value != [None]:
                raise ValueError('by_attribute() att_value list cannot have more than one element if it includes None')
            clone = clone.extra(where=("db_attribute.%s IS NULL" % real_name,))
        else:
            clone = clone.extra(where=("db_attribute.%s IN (%s)" % (real_name, ','.join(['%s' for val in att_value])),),
                                params=tuple(att_value))
        return clone

    def date_counts(self):
        """
        Returns a dictionary mapping {item_date: count}.
        """
        # TODO: values + annotate doesn't seem to play nice with GeoQuerySet
        # at the moment. This is the changeset where it broke:
        # http://code.djangoproject.com/changeset/10326
        from django.db.models.query import QuerySet
        qs = QuerySet.values(self, 'item_date').annotate(count=models.Count('id'))
        return dict([(v['item_date'], v['count']) for v in qs])

    def top_lookups(self, schema_field, count):
        """
        Returns a list of {lookup, count} dictionaries representing the top
        Lookups for this QuerySet.
        """
        # XXX TODO: SPIKIFY
        if schema_field.is_many_to_many_lookup():
            clone = self._clone()
            #clone = clone.extra(where=[real_name + " ~ ('[[:<:]]' || db_lookup.id || '[[:>:]]')"]) XXX
            # We want to count the current queryset and get a single
            # row for injecting into the subsequent Lookup query, but
            # we don't want Django's aggregation support to
            # automatically group by fields that aren't relevant and
            # would cause multiple rows as a result. So we call
            # `values()' on a field that we're already filtering by,
            # in this case, schema, as essentially a harmless identify
            # function.
            clone = clone.values('schema').annotate(count=Count('schema'))
            qs = Lookup.objects.filter(schema_field__id=schema_field.id)
            qs = qs.extra(select={'lookup_id': 'id', 'item_count': clone.values('count').query})
        else:
            #XXX spikify
            qs = self._clone().extra(select={'lookup_id': real_name})
            qs.query.group_by = [real_name]
            qs = qs.values('lookup_id').annotate(item_count=Count('id'))
        ids_and_counts = [(v['lookup_id'], v['item_count']) for v in qs.values('lookup_id', 'item_count').order_by('-item_count') if v['item_count']][:count]
        lookup_objs = Lookup.objects.in_bulk([i[0] for i in ids_and_counts])
        return [{'lookup': lookup_objs[i[0]], 'count': i[1]} for i in ids_and_counts]

    def text_search(self, schema_field, query):
        """
        Returns a QuerySet of NewsItems whose attribute for
        a given schema field matches a text search query.
        """
        # XXX TODO: SPIKIFY
        clone = self._clone()
        query = query.lower()

        clone = clone.extra(where=("db_attribute." + str(schema_field.real_name)
 + " ILIKE %s",),
                            params=("%%%s%%" % query,))
        return clone

class NewsItemManager(models.GeoManager):
    def get_query_set(self, model=None):
        if model is None:
            model = self.model
        return NewsItemQuerySet(model)

    def by_attribute(self, *args, **kwargs):
        return self.get_query_set().by_attribute(*args, **kwargs)

    def text_search(self, *args, **kwargs):
        return self.get_query_set().text_search(*args, **kwargs)

    def date_counts(self, *args, **kwargs):
        return self.get_query_set().date_counts(*args, **kwargs)

    def top_lookups(self, *args, **kwargs):
        return self.get_query_set().top_lookups(*args, **kwargs)


class NewsItem(models.Model):
    """
    Lowest common denominator metadata for News-like things.

    XXX TODO: rewrite this doc

    self.schema and self.attributes are used for extended metadata;
    If all you want is to examine the attributes, self.attributes
    can be treated like a dict.
    (Internally it's a bit complicated. See the Schema, SchemaField, and
    Attribute models, plus AttributeDescriptor, for how it all works.)

    NewsItems have several distinct notions of location:

    * The NewsItemLocation model is for fast lookups of NewsItems to
      all Locations where the .location fields overlap.  This is set
      by a sql trigger whenever self.location changes; not set by any
      python code. Used in various views for filtering.

    * self.location is typically a point, and is used in views for
      filtering newsitems. Theoretically (untested!!) could also be a
      GeometryCollection, for news items that mention multiple
      places. This is typically set during scraping, by geocoding if
      not provided in the source data.

    * self.location_object is a Location and a) is usually Null in
      practice, and b) is only needed by self.location_url(), so we
      can link back to a location view from a newsitem view.  It would
      be set during scraping.  (Example use case: NYC crime
      aggregates, where there's no location or address data for the
      "news item" other than which precinct it occurs in.
      eg. http://nyc.everyblock.com/crime/by-date/2010/8/23/3364632/ )
      XXX consider changing this: ticket #93

    * self.block is optionally one Block. Also set during
      scraping/geocoding.  So far can't find anything that actually
      uses these.

    """

    # We don't have a natural_key() method because we don't know for
    # sure that anything other than ID will be unique.

    schema = models.ForeignKey(Schema)
    title = models.CharField(max_length=255)
    description = models.TextField()
    url = models.TextField(blank=True)
    pub_date = models.DateTimeField(db_index=True)  # TODO: default to now()
    item_date = models.DateField(db_index=True)  # TODO: default to now()
    location = models.GeometryField(blank=True, null=True, spatial_index=True)
    location_name = models.CharField(max_length=255)
    location_object = models.ForeignKey(Location, blank=True, null=True)
    block = models.ForeignKey(Block, blank=True, null=True)
    objects = NewsItemManager()

    @classmethod
    def objects_by_schema(kls, schema):
        """
        Returns a QuerySet that returns subclasses of NewsItem
        """
        if not isinstance(schema, basestring):
            schema = schema.slug
        # XXX TODO: de-hardcode this
        if schema == 'restaurant-inspections':
            model = RestaurantInspection
        elif schema == 'issues':
            model = SeeclickfixIssue
        else:
            model = None
        return kls.objects.get_query_set(model=model)

    attributes = AttributesDescriptor()  # Treat it like a dict. #XXX this can die soon?

    def __unicode__(self):
        return self.title

    def item_url(self):
        return '/%s/by-date/%s/%s/%s/%s/' % (self.schema.slug, self.item_date.year, self.item_date.month, self.item_date.day, self.id)

    def item_url_with_domain(self):
        from django.conf import settings
        return 'http://%s%s' % (settings.EB_DOMAIN, self.item_url())

    def item_date_url(self):
        year = self.item_date.year
        month = self.item_date.month
        day = self.item_date.day
        slug = self.schema.slug
        return '/%(slug)s/by-date/%(year)s-%(month)s-%(day)s,%(year)s-%(month)s-%(day)s/' % locals()

    def location_url(self):
        if self.location_object_id is not None:
            return self.location_object.url()
        return None

    def attributes_for_template(self, *args, **kwargs):
        return []

class AttributeForTemplate(object):
    """Cooks a NewsItem's extensible attributes metadata a bit for
    easier presentation.
    """
    def __init__(self, schema_field, attribute_row):
        self.sf = schema_field

        self.raw_value = attribute_row[schema_field.name]

        self.schema_slug = schema_field.schema.slug
        self.is_lookup = schema_field.is_lookup
        self.is_filter = schema_field.is_filter
        if self.is_lookup:
            if self.raw_value.__class__.__name__ == 'ManyRelatedManager':
                self.values = list(self.raw_value.all())
            else:
                raise AssertionError("new data model hacks: should never get here")
        else:
            self.values = [self.raw_value]

    def value_list(self):
        """
        Returns a list of {value, url, description} dictionaries
        representing each value for this attribute.
        """
        from django.utils.dateformat import format, time_format
        # Setting these to [None] ensures that zip() returns a list
        # of at least length one.
        urls = [None]
        descriptions = [None]
        if self.is_filter:
            if self.is_lookup:
                urls = [look and '/%s/by-%s/%s/' % (self.schema_slug, self.sf.slug, look.slug) or None for look in self.values]
            elif isinstance(self.raw_value, datetime.date):
                urls = ['/%s/by-%s/%s/%s/%s/' % (self.schema_slug, self.sf.slug, self.raw_value.year, self.raw_value.month, self.raw_value.day)]
            elif self.raw_value in (True, False, None):
                urls = ['/%s/by-%s/%s/' % (self.schema_slug, self.sf.slug, {True: 'yes', False: 'no', None: 'na'}[self.raw_value])]
        if self.is_lookup:
            values = [val and val.name or 'None' for val in self.values]
            descriptions = [val and val.description or None for val in self.values]
        elif isinstance(self.raw_value, datetime.datetime):
            values = [format(self.raw_value, 'F j, Y, P')]
        elif isinstance(self.raw_value, datetime.date):
            values = [format(self.raw_value, 'F j, Y')]
        elif isinstance(self.raw_value, datetime.time):
            values = [time_format(self.raw_value, 'P')]
        elif self.raw_value is True:
            values = ['Yes']
        elif self.raw_value is False:
            values = ['No']
        elif self.raw_value is None:
            values = ['N/A']
        else:
            values = [self.raw_value]
        return [{'value': value, 'url': url, 'description': description} for value, url, description in zip(values, urls, descriptions)]


class LookupManager(models.Manager):

    def get_by_natural_key(self, slug, schema_field__slug,
                           schema_field__real_name):
        return self.get(slug=slug, schema_field__slug=schema_field__slug,
                        schema_field__real_name=schema_field__real_name)

    def get_or_create_lookup(self, schema_field, name, code=None, description='', make_text_slug=True, logger=None):
        """
        Returns the Lookup instance matching the given SchemaField, name and
        Lookup.code, creating it (with the given name/code/description) if it
        doesn't already exist.

        If make_text_slug is True, then a slug will be created from the given
        name. If it's False, then the slug will be the Lookup's ID.
        """
        def log_info(message):
            if logger is None:
                return
            logger.info(message)
        def log_warn(message):
            if logger is None:
                return
            logger.warn(message)
        code = code or name # code defaults to name if it wasn't provided
        try:
            obj = Lookup.objects.get(schema_field__id=schema_field.id, code=code)
        except Lookup.DoesNotExist:
            if make_text_slug:
                slug = slugify(name)
                if len(slug) > 32:
                    # Only bother to warn if we're actually going to use the slug.
                    if make_text_slug:
                        log_warn("Trimming slug %r to %r in order to fit 32-char limit." % (slug, slug[:32]))
                    slug = slug[:32]
            else:
                # To avoid integrity errors in the slug when creating the Lookup,
                # use a temporary dummy slug that's guaranteed not to be in use.
                # We'll change it back immediately afterward.
                slug = '__3029j3f029jf029jf029__'
            if len(name) > 255:
                old_name = name
                name = name[:250] + '...'
                # Save the full name in the description.
                if not description:
                    description = old_name
                log_warn("Trimming name %r to %r in order to fit 255-char limit." % (old_name, name))
            obj = Lookup(schema_field_id=schema_field.id, name=name, code=code, slug=slug, description=description)
            obj.save()
            if not make_text_slug:
                # Set the slug to the ID.
                obj.slug = obj.id
                obj.save()
            log_info('Created %s %r' % (schema_field.name, name))
        return obj

class Lookup(models.Model):
    """
    Used to normalize NewsItem attribute values where there are a
    smallish set of possible values.
    """
    schema_field = models.ForeignKey(SchemaField)
    name = models.CharField(max_length=255)
    # `code` is the optional internal code to use during retrieval.
    # For example, in scraping Chicago crimes, we use the crime type code
    # to find the appropriate crime type in this table. We can't use `name`
    # in that case, because we've massaged `name` to use a "prettier"
    # formatting than exists in the data source.
    code = models.CharField(max_length=255, blank=True)
    slug = models.CharField(max_length=32, db_index=True)
    description = models.TextField(blank=True)

    objects = LookupManager()

    class Meta:
        unique_together = (('slug', 'schema_field'),)

    def natural_key(self):
        return (self.slug, self.schema_field.schema.slug,
                self.schema_field.real_name)

    def __unicode__(self):
        return u'%s - %s' % (self.schema_field, self.name)

class NewsItemLocation(models.Model):
    news_item = models.ForeignKey(NewsItem)
    location = models.ForeignKey(Location)

    class Meta:
        unique_together = (('news_item', 'location'),)

    def __unicode__(self):
        return u'%s - %s' % (self.news_item, self.location)

class AggregateBaseClass(models.Model):
    schema = models.ForeignKey(Schema)
    total = models.IntegerField()

    class Meta:
        abstract = True

class AggregateAll(AggregateBaseClass):
    # Total items in the schema.
    pass

class AggregateDay(AggregateBaseClass):
    # Total items in the schema with item_date on the given day
    date_part = models.DateField(db_index=True)

class AggregateLocation(AggregateBaseClass):
    # Total items in the schema in location, summed over that last 30 days
    location_type = models.ForeignKey(LocationType)
    location = models.ForeignKey(Location)

class AggregateLocationDay(AggregateBaseClass):
    # Total items in the schema in location with item_date on the given day
    location_type = models.ForeignKey(LocationType)
    location = models.ForeignKey(Location)
    date_part = models.DateField(db_index=True)

class AggregateFieldLookup(AggregateBaseClass):
    # Total items in the schema with schema_field's value = lookup
    schema_field = models.ForeignKey(SchemaField)
    lookup = models.ForeignKey(Lookup)

class SearchSpecialCase(models.Model):
    query = models.CharField(max_length=64, unique=True)
    redirect_to = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=128, blank=True)
    body = models.TextField(blank=True)

    def __unicode__(self):
        return self.query

class DataUpdate(models.Model):
    # Keeps track of each time we update our data.
    schema = models.ForeignKey(Schema)
    update_start = models.DateTimeField()  # When the scraper/importer started running.
    update_finish = models.DateTimeField() # When the scraper/importer finished.
    num_added = models.IntegerField()
    num_changed = models.IntegerField()
    num_deleted = models.IntegerField()
    num_skipped = models.IntegerField()
    got_error = models.BooleanField()

    def __unicode__(self):
        return u'%s started on %s' % (self.schema.name, self.update_start)

    def total_time(self):
        return self.update_finish - self.update_start


#####################################
# DATAMODEL SPIKE HACK MODELS
#####################################

from UserDict import DictMixin

class AttributeDict2(DictMixin):

    """Preserve the old dictionary-like API for newsitem.attributes,
    while actually storing the data in fields on the newsitem.

    XXX deprecate this API?
    """

    def __init__(self, newsitem):
        self.newsitem = newsitem

    def __setitem__(self, key, val):
        if key not in self.newsitem.attribute_keys:
            raise KeyError("unexpected key %r" % key)
        if isinstance(val, list):
            # Possibly m2m lookup.
            field = getattr(self.newsitem, key)
            # hackery, can't use isinstance() when the class is built on
            # the fly:
            if field.__class__.__name__ == 'ManyRelatedManager':
                field.clear()
                field.add(*val)
            else:
                raise AssertionError("should not get here")
        else:
            setattr(self.newsitem, key, val)

    def __getitem__(self, key):
        try:
            return getattr(self.newsitem, key)
        except AttributeError:
            raise KeyError(key)

    def keys(self):
        return self.newsitem.attribute_keys

    # XXX do we need __delitem__() ?


class NewStyleAttributesMixin(object):

    _attrdict = None

    def _get_attributes(self):
        #print "XXX datamodel spike: getting new .attributes() property"
        if self._attrdict is None:
            self._attrdict = AttributeDict2(self)
        return self._attrdict

    def _set_attributes(self, adict):
        self._attrdict = AttributeDict2(self)
        self._attrdict.update(adict)

    attributes = property(_get_attributes, _set_attributes)

    # XXX backward compatibility with undocumented result of
    # db.utils.populate_attributes_if_needed(), used by some templates.
    @property
    def attribute_values(self):
        return self._get_attributes()

    def attributes_for_template(self):
        """
        Return a list of AttributeForTemplate objects for this NewsItem. The
        objects are ordered by SchemaField.display_order.
        """
        print "XXX datamodel spike: new attributes_for_template()"
        from ebpub.db.models import AttributeForTemplate, SchemaField
        fields = SchemaField.objects.filter(schema__id=self.schema_id).select_related().order_by('display_order')
        if not fields:
            return []
        attribute_row = self.attributes
        return [AttributeForTemplate(f, attribute_row) for f in fields]

class SeeclickfixIssue(NewStyleAttributesMixin, NewsItem):

    rating = models.IntegerField(null=True)
    attribute_keys = ('rating',)
    schemaslug = 'issues'


class RestaurantInspection(NewStyleAttributesMixin, NewsItem):

    # We use a lot of limit_choices_to=Q(...) as per
    # http://docs.djangoproject.com/en/1.2/ref/models/fields/#django.db.models.ForeignKey.limit_choices_to
    # to filter out irrelevant foreign keys from the add/edit admin UI.

    # XXX can't do that on NewsItem.schema because in multi-table inheritance,
    # subclasses can't override a base class' field.
    # Wish limit_choices_to was part of ModelAdmin rather than Model.

    attribute_keys = ('inspection_id', 'restaurant_id',
                      'restaurant_name', 'result',
                      'violation', 'details')

    schemaslug = 'restaurant-inspections'

    # XXX allowing null=True on all of them b/c we need to have a primary
    # key before we can do a many-to-many field, and we typically assign these
    # all in a batch, so we'll rely on app code to ensure these are non-Null.
    # Which was the case in the old data model anyway.

    inspection_id = models.IntegerField(null=True)
    restaurant_id = models.IntegerField(null=True)
    restaurant_name = models.CharField(max_length=255, null=True)

    # XXX TODO:
    # possibly use a single table for all our ManyToManyFields?
    # can we then do one query for all lookups across NewsItem subclasses? See
    # http://docs.djangoproject.com/en/1.2/ref/models/fields/#django.db.models.ManyToManyField.through
    #
    # Also, we don't have a reverse query attribute on Lookup because
    # it's probably not that useful given that the names have to be different
    # to avoid clashes; so we disable them by setting related_name='foo+'.
    # ... or maybe we could use & assume a naming convention?

    result = models.ManyToManyField(
        Lookup, related_name='result+', null=True,
        limit_choices_to=Q(schema_field__name='result'))
    violation = models.ManyToManyField(
        Lookup, related_name='violation+', null=True,
        limit_choices_to=Q(schema_field__name='violation'))
    details = models.TextField(null=True, blank=True)



