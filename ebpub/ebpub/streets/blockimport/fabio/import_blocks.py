#!/usr/bin/env python
#   Copyright 2007,2008,2009,2011 Everyblock LLC, OpenPlans, and contributors
#
#   This file is part of ebpub
#
#   ebpub is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   ebpub is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with ebpub.  If not, see <http://www.gnu.org/licenses/>.
#

import sys
import optparse
import psycopg2
from django.contrib.gis.gdal import DataSource
from ebdata.parsing import dbf
from ebpub.streets.blockimport.base import BlockImporter


class CartociudadImporter(BlockImporter):


    def __init__(self):
	def _damemenor(x,y):
		if x < y:
			return x
		else:
			return y
	def _damemayor(x,y):
		if x > y:
			return x
		else:
			return y



	try:
       		conn1 = psycopg2.connect("dbname='cartociudad' user='fabio' host='localhost' password='12345'");
       		conn2 = psycopg2.connect("dbname='openblock_madridblock' user='fabio' host='localhost' password='12345'");
   	except:
       		print "I am unable to connect to the database"

	cur1 = conn1.cursor()
	cur1.execute("""SELECT nom_via,par_bajo,par_alto,imp_bajo,imp_alto,tip_via,st_astext(the_geom) from tramos limit 5""")
	rows = cur1.fetchall()
	cur2 = conn2.cursor()
	for row in rows:
    		print row
		nom_via = row[0]
		limite_bajo = _damemenor(row[1],row[3])
		limite_alto = _damemayor(row[2],row[4])
		tip_via = row[5]
		geom = row[6]
		street_pretty_name = str(tip_via) + " " + str(nom_via)
		pretty_name = street_pretty_name + " " + str(limite_bajo) + " - " + str(limite_alto)
		cur2.execute(
	     		"""INSERT INTO blocks (pretty_name,predir,left_from_num,left_to_num,right_from_num,right_to_num,street,street_slug,street_pretty_name,suffix,postdir,left_city,right_city,left_state,right_state,geom)
        		VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, ST_GeomFromText(%s));""",
			(pretty_name,'',row[1],row[2],row[3],row[4],nom_via,'slug',street_pretty_name,tip_via,'','Madrid','Madrid','ES','ES',geom))

	cur1.close()
	conn1.close()
	cur2.close()
	conn2.close()

	
def main(argv=None):
    tiger = CartociudadImporter()


if __name__ == '__main__':
    sys.exit(main())
