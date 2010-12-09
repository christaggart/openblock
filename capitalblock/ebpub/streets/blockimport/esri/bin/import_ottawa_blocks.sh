#!/bin/bash

# Based on http://wiki.github.com/dkukral/everyblock/install-everyblock

HERE=`(cd "${0%/*}" 2>/dev/null; echo "$PWD"/)`
SOURCE_ROOT=`cd $HERE/../.. && pwd`
echo Source root is $SOURCE_ROOT


function die {
    echo $@ >&2
    echo Exiting.
    exit 1
}


if [ ! -n "$DJANGO_SETTINGS_MODULE" ]; then
    die "Please set DJANGO_SETTINGS_MODULE to your projects settings module"
fi


# First we download a bunch of zipfiles of ESRI data.

BASEURL=http://www.ottawa.ca/online_services/opendata/data/
ZIPS="ottawaroads.zip"

mkdir -p ottawa_data
cd ottawa_data || die "couldn't cd to $PWD/ottawa_data"

for fname in $ZIPS; do
    wget -N $BASEURL/$fname
    if [ $? -ne 0 ]; then
        die "Could not download $BASEURL/$fname"
    fi
done

for fname in *zip; do unzip -o $fname; done
echo Shapefiles unzipped in $PWD/ottawa_data

# Now we load them into our blocks table.


IMPORTER=$SOURCE_ROOT/capitalblock/bin/blocks_ottawa.py
if [ ! -f "$IMPORTER" ]; then die "Could not find import_blocks.py at $IMPORTER" ; fi

echo Importing blocks, this may take several minutes ...

# Passing --city means we skip features labeled for other cities.
$IMPORTER ottawaRoads.shp || die

#########################

echo Populating streets and fixing addresses, these can take several minutes...

cd $SOURCE_ROOT/ebpub/ebpub/streets/bin || die

./populate_streets.py -v -v -v -v streets || die
./populate_streets.py -v -v -v -v block_intersections || die
./populate_streets.py -v -v -v -v intersections || die

echo Done.
