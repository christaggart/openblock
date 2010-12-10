import re
import string
import sys
import optparse
from django.contrib.gis.gdal import DataSource
from ebpub.metros.models import Metro
from ebpub.streets.models import Block
from ebpub.streets.name_utils import make_pretty_name
from ebpub.utils.text import slugify

FIELD_MAP = {
    # ESRI        # Block
    'LEFT_FROM'   : 'left_from_num',
    'LEFT_TO'   : 'left_to_num',
    'RIGHT_FROM'   : 'right_from_num',
    'RIGHT_TO'   : 'right_to_num',
#    'POSTAL_L'  : 'left_zip',
#    'POSTAL_R'  : 'right_zip',
#    'GEONAME_L' : 'left_city',
#    'GEONAME_R' : 'right_city',
#    'STATE_L'   : 'left_state',
#    'STATE_R'   : 'right_state',
}

NAME_FIELD_MAP = {
    'RD_NAME'      : 'street',
    'RD_SUFFIX'      : 'suffix',
   # 'RD_PREFIX'    : 'predir',
    'RD_DIRECTI'    : 'postdir',
}

# FCC == feature classification code: indicates the type of road
VALID_FCC_PREFIXES = (
    'A1', # primary highway with limited access
    'A2', # primary road without limited access
    'A3', # secondary and connecting road
    'A4'  # local, neighborhood, and rural road
)

ENCODING = 'cp1252'

print >> sys.stderr, 'Starting block importer.'

class EsriImporter(object):
    def __init__(self, shapefile, city=None, layer_id=0):
        print >> sys.stderr, 'Opening %s' % shapefile
        ds = DataSource(shapefile)

        self.layer = ds[layer_id]
        self.city = "OTTAWA" #city and city or Metro.objects.get_current().name
        self.fcc_pat = re.compile('^(' + '|'.join(VALID_FCC_PREFIXES) + ')\d$')

    def save(self, verbose=False):
        alt_names_suff = (u'',)
        num_created = 0
        for i, feature in enumerate(self.layer):
            #if not self.fcc_pat.search(feature.get('FCC')):
            #    continue
            parent_id = None
            fields = {}
            for esri_fieldname, block_fieldname in FIELD_MAP.items():
                value = feature.get(esri_fieldname)
                #print >> sys.stderr, 'Looking at %s' % esri_fieldname

                if isinstance(value, basestring):
                    value = value.upper()
                elif isinstance(value, int) and value == 0:
                    value = None
                fields[block_fieldname] = value
            if not ((fields['left_from_num'] and fields['left_to_num']) or
                    (fields['right_from_num'] and fields['right_to_num'])):
                continue
            # Sometimes the "from" number is greater than the "to"
            # number in the source data, so we swap them into proper
            # ordering
            for side in ('left', 'right'):
                from_key, to_key = '%s_from_num' % side, '%s_to_num' % side
                if fields[from_key] > fields[to_key]:
                    fields[from_key], fields[to_key] = fields[to_key], fields[from_key]
            if feature.geom.geom_name != 'LINESTRING':
                continue
            for suffix in alt_names_suff:
                name_fields = {}
                for esri_fieldname, block_fieldname in NAME_FIELD_MAP.items():
                    key = esri_fieldname + suffix
                    name_fields[block_fieldname] = feature.get(key).upper()
                    #if block_fieldname == 'postdir':
                        #print >> sys.stderr, 'Postdir block %s' % name_fields[block_fieldname]


                if not name_fields['street']:
                    continue
                # Skip blocks with bare number street names and no suffix / type
                if not name_fields['suffix'] and re.search('^\d+$', name_fields['street']):
                    continue
                fields.update(name_fields)
                for key, val in fields.items():
                    if isinstance(val, str):
                        fields[key] = val.decode(ENCODING)

                fields['street_pretty_name'], fields['pretty_name'] = make_pretty_name(
                    fields['left_from_num'],
                    fields['left_to_num'],
                    fields['right_from_num'],
                    fields['right_to_num'],
                    u'',
                    fields['street'],
                    fields['suffix'],
                    fields['postdir'],
                )

                #print >> sys.stderr, 'Looking at block pretty name %s' % fields['street']

                fields['street_slug'] = slugify(u' '.join((fields['street'], fields['suffix'])))

                # Watch out for addresses like '247B' which can't be
                # saved as an IntegerField.
                for addr_key in ('left_from_num', 'left_to_num', 'right_from_num', 'right_to_num'):
                    fields[addr_key] = fields[addr_key].rstrip(string.letters)
                block = Block(**fields)
                block.geom = feature.geom.geos
                print >> sys.stderr, u'Looking at block %s' % fields['street']

                block.save()

                if parent_id is None:
                    parent_id = block.id
                else:
                    block.parent_id = parent_id
                    block.save()
                num_created += 1
                #if verbose:
                print >> sys.stderr, 'Created block %s' % block
        return num_created



def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = optparse.OptionParser(usage='%prog edges.shp')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False)
    parser.add_option('-c', '--city', dest='city', help='A city name to filter against')
    (options, args) = parser.parse_args(argv)
    if len(args) != 1:
        return parser.error('must provide at least 1 arguments, see usage')
    args.append(options.city)
    args.append(options.verbose)
    esri = EsriImporter(*args)
    num_created = esri.save(options.verbose)
    #if options.verbose:
    #    print "Created %d blocks" % num_created

if __name__ == '__main__':
    sys.exit(main())
