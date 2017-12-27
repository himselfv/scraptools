import argparse
import os
import errno
import codecs
import shutil
import rdflib
import logging
import lxml.html
import mhtml

logging.basicConfig()

parser = argparse.ArgumentParser(description="Reads Scrapbook/Scrapbook X data and allows to inspect and convert it")
parser.add_argument("--from", type=str, required=True, dest="from_path", metavar="PATH", help="path to Scrapbook data folder (usually in your Firefox profile)")
parser.add_argument("--convert", type=str, metavar="FOLDER", help="convert contents to files and folders and place in this folder")
parser.add_argument("--dumpitems", action='store_true', help="dump flat item list")
parser.add_argument("--dumpprops", type=str, help="dump flat property list for this item")
parser.add_argument("--item", type=str, help="print this items' properties")
parser.add_argument("--verbose", action='store_true', help="print detailed status messages")
parser.add_argument("--mht", action='store_true', help="store saved pages as MHT instead of folders")
parser.add_argument("--local-props", action='store_true', help="for properties which could not have been stored internally in the file format, store them in an additional file instead of just in the directory index")
args = parser.parse_args()


# TODO: date fields (create / modify): parse; store as available

# namespaces
RDF = rdflib.Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
NS1 = rdflib.Namespace("http://amb.vis.ne.jp/mozilla/scrapbook-rdf#")
NC = rdflib.Namespace("http://home.netscape.com/NC-rdf#")


if args.verbose: print "Loading scrapbook.rdf..."
g = rdflib.Graph()
g.parse(args.from_path+"/scrapbook.rdf")


# Read into a flat 2-level item[].property[] list
if args.verbose: print "Reading items..."
items = dict()
for itemname, propname, value in g:
	itemname = itemname.toPython() # to string, or triggers strange behavior
	if itemname.startswith("urn:scrapbook:search"):
		# Dunno what's this but we don't care
		continue
	if itemname.startswith("urn:scrapbook:item"):
		itemname = itemname[18:]
	# There's also urn:scrapbook:root which is a root folder
	item = items.setdefault(itemname, dict())
	
	propname = propname.toPython()
	if propname.startswith(NS1):
		propname = 'NS1:'+propname[len(NS1):]
	elif propname.startswith(RDF):
		propname = 'RDF:'+propname[len(RDF):]
	
	if value.startswith("urn:scrapbook:item"):
		value = value[18:]
	
	item[propname] = value
	
	#print itemname, propname



# Turn into a tree

# Makes a string suitable to be file name + id (no equality signs)
def neuter_name(name):
    reserved_chars ='\\/:*?"<>|='
    for char in reserved_chars:
        name = name.replace(char, '')
    return name

class Prop(object):
	def __init__(self, name, value):
		self.name = name
		self.value = value

class Node(object):
	def __init__(self, id, item):
		# This can be created with item==None, for lost folders
		self.id = id
		self.children = []
		
		self.type = unicode(item['NS1:type']) if item is not None else ''
		
		if item is not None:
			title = unicode(item.get('NS1:title', '')) # root has no title
		else:
			title = id
		
		# Name is a neutered title, suitable for use as filename and ini-id
		self.name = neuter_name(title).strip()
		# Folders in Windows fail when name ends with dots
		# We could've tested for type==folder, but some other types end up as folders too,
		# so it's safer to just prohibit this at all.
		# Spaces too.
		self.name = self.name.rstrip('. ').lstrip(' ')
		if self.name == '':
			self.name = self.id # guaranteed to be safe

		# remember to store original name as "customized" if neuter changed it
		self.customtitle = title if title != self.name else None

		self.comment = unicode(item.get('NS1:comment', '')) if item is not None else ''
		self.source = unicode(item.get('NS1:source', '')) if item is not None else ''
		self.icon = unicode(item.get('NS1:icon', '')) if item is not None else ''
		if self.icon.startswith('resource://scrapbook/data/'+self.id+'/'):
			self.icon = self.icon[len('resource://scrapbook/data/'+self.id+'/'):]
		
		self.create = unicode(item.get('NS1:create', '')) if item is not None else ''
		self.modify = unicode(item.get('NS1:modify', '')) if item is not None else ''

		self.props = [] # any additional props this node fails to store internally


def load_node(id, item):
	if 'node' in item:
		return item['node'] # do not create a second one

	node = Node(id, item)
	if node.type == 'folder':
		idx = 1
		while 'RDF:_'+str(idx) in item:
			subitemid = item['RDF:_'+str(idx)]
			subitem = items[subitemid]
			subnode = load_node(subitemid, subitem)
			node.children += [subnode]
			idx += 1
	else:
		assert('RDF:_1' not in item) # should not have child items
		if node.type == 'note':
			# text note
			# title == first line
			# icon can't be changed
			# no formatting
			pass
		elif node.type == 'notex':
			# note with additional formatting
			# title can be changed arbitrarily
			# icon can be changed
			# limited formatting
			pass
		else:
			# saved page
			pass
	
	item['node'] = node # set backreference
	return node

if args.verbose: print "Building tree..."
items['urn:scrapbook:root']['NS1:type']='folder' # force explicit
root = load_node('', items['urn:scrapbook:root'])


# Attaches all items without a parent to a root folder
def fix_lost_items():
	global items, root
	lost_items = 0
	for key, item in items.iteritems():
		if item['node'] is None:
			lost_items += 1
			root.children += [load_node(key, item)]
	return lost_items

lost_items = fix_lost_items()
if lost_items > 0:
	print "Lost items: "+str(lost_items)


def subfiles(a_dir):
    return [name for name in os.listdir(a_dir)
            if os.path.isfile(os.path.join(a_dir, name))]

def subdirs(a_dir):
    return [name for name in os.listdir(a_dir)
            if os.path.isdir(os.path.join(a_dir, name))]

# Adds an entry for every data directory lacking an entry
def fix_lost_folders():
	global items, root, args
	lost_folders = 0
	for dir in subdirs(args.from_path+'\\data'):
		if dir in items: continue
		if args.verbose: print "Found lost folder: %s" % dir
		node = Node(dir, None)
		# try to guess the node type
		files = subfiles(args.from_path+'\\data\\'+dir)
		if (len(files) == 1) and (files[0].lower() == 'index.html'):
			node.type = "note"
		else:
			node.type = ""
		root.children += [node]
		lost_folders += 1
	return lost_folders

lost_folders = fix_lost_folders()
if lost_folders > 0:
	print "Lost folders: "+str(lost_folders)



# Printing

def dump_items():
	for itemname, item in items.iteritems():
		print itemname + '=' + str(len(item.keys()))

def dump_props(item):
	for propname in item.keys():
		print propname

def print_node(node):
	print node.name
	if hasattr(node, 'items'):
		for subnode in node.children:
			if hasattr(subnode, 'items'):
				print subnode.id + '   \\' + subnode.name # subfolder
			else:
				print subnode.id + '   ' + subnode.name # file

def touch_path(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise

def encode_ini_value(value):
	return value # TODO: replace CRLF and invalid chars

# Writes additional properties for a folder-like item to desktop.ini
def write_desktop_ini(folder, node):
	# see https://msdn.microsoft.com/en-us/library/windows/desktop/cc144102%28v=vs.85%29.aspx
	desc = codecs.open(folder+'\\desktop.ini', 'w', 'utf-16') # encoding supported by windows
	
	if node.source:
		desc.write('[Scrapbook]\r\n')
		if node.source: desc.write('Source='+encode_ini_value(node.source)+'\r\n')
		desc.write('\r\n')

	if node.customtitle or node.comment or node.icon: # also write Windows-compatible version
		desc.write('[.ShellClassInfo]\r\n')
		if node.customtitle: desc.write('LocalizedResourceName='+encode_ini_value(node.customtitle)+'\r\n')
		if node.comment: desc.write('InfoTip='+encode_ini_value(node.comment)+'\r\n')
		if node.icon: desc.write('IconResource='+encode_ini_value(node.icon)+'\r\n')

	had_props = False
	if node.children and (len(node.children) > 0):
		# Write alternative names and children order
		desc.write('[Scrapbook:Index]\r\n')
		for subnode in node.children:
			if subnode.customtitle:
				desc.write(subnode.name+'='+encode_ini_value(subnode.customtitle)+'\r\n')
			else:
				desc.write(subnode.name+"\r\n")
			if subnode.props:
				had_props = True
		desc.write('\r\n')

	if had_props:
		desc.write('[Scrapbook:Properties]\r\n')
		for subnode in node.children:
			if not subnode.props: continue
			for prop in subnode.props:
				desc.write(subnode.name+':'+prop.name+'='+encode_ini_value(prop.value)+'\r\n');
		desc.write('\r\n')

	desc.close()
	
	# Set system and hidden attributes to tell Windows to read desktop.ini
	import win32con, win32api, os
	short_unc = win32api.GetShortPathName(folder) # SetFileAttributes fails on some longer/non-unicode names
	win32api.SetFileAttributes(short_unc, win32con.FILE_ATTRIBUTE_SYSTEM or win32con.FILE_ATTRIBUTE_HIDDEN)

def convert_node(node, output_dir):
	global args
	if args.verbose: print "Converting %s..." % node.id

	if node.type == 'folder':
		if node.name == "": # special case: root folder
			node_dir = output_dir
		else:
			node_dir = output_dir+'\\'+node.name
		touch_path(node_dir)

		# First convert children, so that they formulate all of their external properties
		for subnode in node.children:
			convert_node(subnode, node_dir)

		# Now write full desktop.ini
		write_desktop_ini(node_dir, node)

	elif node.type == 'note':
		tree = lxml.html.parse(open(args.from_path+'\\data\\'+node.id+'\\index.html'))
		matches = tree.xpath('/html/body/pre')
		assert(matches[0] is not None)

		#Do not use text_content() as it kills any internal tags (even if they're meant to be the content)
		#due to the way Scrapbook stores those (without html-encoding).
		
		#Do not just do:
		#  text = lxml.etree.tostring(matches[0], encoding=unicode)
		#As this will also print the tag itself.
		
		#Print the text before any children + children itself:
		text = (matches[0].text or '') + ''.join([lxml.html.tostring(child, encoding=unicode) for child in matches[0].iterdescendants()])

		# Text starts on the next line after <pre> tag, so remove one linefeed
		if text[:1] == '\n': text = text[1:]

		f = codecs.open(output_dir+'\\'+node.name+'.txt', 'w', 'utf-8')
		f.write(text)
		f.close()

		# Notes don't need customtitle: they always use first line as title
		# They also can't have custom icon/source, but we'll keep the option just in case
		if args.local_props and (node.comment or node.source or node.icon):
			desc = codecs.open(output_dir+'\\'+node.name+'.dat', 'w', 'utf-8')
			if node.comment: desc.write('Comment='+node.comment+'\r\n')
			if node.source: desc.write('Source='+node.source+'\r\n')
			if node.icon: desc.write('Icon='+node.icon+'\r\n')
			desc.close()
		
		node.props = []
		if node.comment: node.props.append(Prop('comment', node.comment))
		if node.source: node.props.append(Prop('source', node.source))
		if node.icon: node.props.append(Prop('icon', node.icon))

	else: # saved document or notex
		if args.mht:
			# Store as .mht
			mht = mhtml.MHTML()
			mht.content_location = "" # do not store absolute locations
			mht.from_folder(args.from_path+'\\data\\'+node.id)

			# Store additional properties as appropriate standard headers
			if node.customtitle: mht.content['Subject'] = node.customtitle
			if node.comment: mht.content['Comments'] = node.comment
			if node.source: mht.content['Content-Location'] = node.source
			# favicon.ico is assumed by default: this way foreign .mht has a chance at having an icon too
			if node.icon and (node.icon != 'favicon.ico'): mht.content['Icon'] = node.icon
			
			# Has additional properties
			# NS1:create="20150909122950"  -- "Date" header?
	        # NS1:modify="20150909122950"
	        # NS1:lock

			mht.save_to_file(output_dir+'\\'+node.name+'.mht')
		else:
			# Store as folder
			if os.path.exists(args.from_path+'\\data\\'+node.id): # must be a folder
				shutil.copytree(args.from_path+'\\data\\'+node.id, output_dir+'\\'+node.name)
			else:
				os.mkdir(output_dir+'\\'+node.name)
			if node.customtitle or node.comment or node.source or node.icon:
				write_desktop_ini(output_dir+'\\'+node.name, node)


if args.convert is not None:
	convert_node(root, args.convert)
elif args.dumpprops is not None:
	dump_props(items[args.dumpprops])
elif args.dumpitems:
	dump_items()
elif args.item is not None:
	print_node(items[args.item]['node'])
else:
	print_node(root)
