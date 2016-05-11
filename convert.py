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

parser = argparse.ArgumentParser(description="Works with scrapbook.rdf")
parser.add_argument("--dumpitems", action='store_true', help="dump flat item list")
parser.add_argument("--dumpprops", type=str, help="dump flat property list for this item")
parser.add_argument("--item", type=str, help="print this items' properties")
parser.add_argument("--convert", type=str, help="convert to text files and place in this folder")
parser.add_argument("--verbose", action='store_true', help="print detailed status messages")
parser.add_argument("--mht", action='store_true', help="store saved pages as MHT instead of folders")
args = parser.parse_args()


# TODO: date fields (create / modify): parse; store as available

# namespaces
RDF = rdflib.Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
NS1 = rdflib.Namespace("http://amb.vis.ne.jp/mozilla/scrapbook-rdf#")
NC = rdflib.Namespace("http://home.netscape.com/NC-rdf#")


if args.verbose: print "Loading scrapbook.rdf..."
g = rdflib.Graph()
g.parse("scrapbook.rdf")


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
class Node(object):
	def __init__(self, id, item):
		self.id = id
		self.item = item
		self.children = []
		self.type = ""
		if item is not None:
			self.name = item.get('NS1:title', '') # root has no title
		else:
			self.name = id
	
	@property
	def comment(self):
		return unicode(self.item.get('NS1:comment', '')) if self.item is not None else ''
	
	@property
	def source(self):
		return unicode(self.item.get('NS1:source', '')) if self.item is not None else ''

	@property
	def icon(self):
		return unicode(self.item.get('NS1:icon', '')) if self.item is not None else ''

	@property
	def create(self):
		return unicode(self.item.get('NS1:create', '')) if self.item is not None else ''

	@property
	def modify(self):
		return unicode(self.item.get('NS1:modify', '')) if self.item is not None else ''



def load_node(id, item):
	if 'node' in item:
		return item['node'] # do not create a second one

	node = Node(id, item)

	node.type = unicode(item['NS1:type'])
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
	for dir in subdirs('.\\data'):
		if dir in items: continue
		if args.verbose: print "Found lost folder: %s" % dir
		node = Node(dir, None)
		# try to guess the node type
		files = subfiles('.\\data\\'+dir)
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

# Makes a string suitable to be file name
def neuter_name(name):
    reserved_chars ='\\/:*?"<>|'
    for char in reserved_chars:
        name = name.replace(char, '')
    return name

# Writes additional properties for a folder-like item to desktop.ini
def write_desktop_ini(folder, title, comment, source, icon):
	# see https://msdn.microsoft.com/en-us/library/windows/desktop/cc144102%28v=vs.85%29.aspx
	desc = codecs.open(folder+'\\desktop.ini', 'w', 'utf-16') # encoding supported by windows
	if title or source or icon:
		desc.write('[Scrapbook]\r\n')
		if title: desc.write('Title='+title+'\r\n')
		if source: desc.write('Source='+source+'\r\n')
		if icon: desc.write('Icon='+icon+'\r\n')
		desc.write('\r\n')
	if comment: # also write Windows-compatible version
		desc.write('[.ShellClassInfo]\r\n')
		desc.write('InfoTip='+comment+'\r\n')
	desc.close()
	
	# Set system and hidden attributes to tell Windows to read desktop.ini
	import win32con, win32api, os
	short_unc = win32api.GetShortPathName(folder) # SetFileAttributes fails on some longer/non-unicode names
	win32api.SetFileAttributes(short_unc, win32con.FILE_ATTRIBUTE_SYSTEM or win32con.FILE_ATTRIBUTE_HIDDEN)

def convert_node(node, output_dir):
	global args
	if args.verbose: print "Converting %s..." % node.id
	
	nodename = neuter_name(node.name).strip()
	if nodename == '':
		nodename = node.id # guaranteed to be safe
	# remember to store original name as "customized" if neuter changed it

	customtitle = unicode(node.name) if unicode(node.name) != nodename else None
	comment = node.comment
	source = node.source
	icon = node.icon
	if icon.startswith('resource://scrapbook/data/'+node.id+'/'):
		icon = icon[len('resource://scrapbook/data/'+node.id+'/'):]
	create = node.create
	modify = node.modify

	if node.type == 'folder':
		if node.name == "": # special case: root folder
			node_dir = output_dir
		else:
			node_dir = output_dir+'\\'+nodename
		touch_path(node_dir)

		desc = codecs.open(node_dir+'\\index', 'w', 'utf-8')
		# Write contents order
		for subnode in node.children:
			desc.write(subnode.name+"\r\n")
		desc.close()
		
		if customtitle or comment or source or icon:
			write_desktop_ini(node_dir, customtitle, comment, source, icon)

		for subnode in node.children:
			convert_node(subnode, node_dir)

	elif node.type == 'note':
		tree = lxml.html.parse(codecs.open('data\\'+node.id+'\\index.html'))
		matches = tree.xpath('/html/body/pre')
		assert(matches[0] is not None)
		text = matches[0].text_content()
		# Text starts on the next line after <pre> tag, so remove one linefeed
		if text[:1] == '\n': text = text[1:]

		f = codecs.open(output_dir+'\\'+nodename+'.txt', 'w', 'utf16')
		f.write(text)
		f.close()

		# Notes don't need customtitle: they always use first line as title
		# They also can't have custom icon/source, but we'll keep the option just in case
		if comment or source or icon:
			desc = codecs.open(output_dir+'\\'+nodename+'.dat', 'w', 'utf-16')
			if comment: desc.write('Comment='+comment+'\r\n')
			if source: desc.write('Source='+source+'\r\n')
			if icon: desc.write('Icon='+icon+'\r\n')
			desc.close()

	else: # saved document or notex
		if args.mht:
			# Store as .mht
			mht = mhtml.MHTML()
			mht.content_location = "" # do not store absolute locations
			mht.from_folder('data\\'+node.id)

			# Store additional properties as appropriate standard headers
			if customtitle: mht.content['Subject'] = customtitle
			if comment: mht.content['Comments'] = comment
			if source: mht.content['Content-Location'] = source
			# favicon.ico is assumed by default: this way foreign .mht has a chance at having an icon too
			if icon and (icon != 'favicon.ico'): mht.content['Icon'] = icon
			
			# Has additional properties
			# NS1:create="20150909122950"  -- "Date" header?
	        # NS1:modify="20150909122950"
	        # NS1:lock

			mht.save_to_file(output_dir+'\\'+nodename+'.mht')
		else:
			# Store as folder
			if nodename.endswith('.'):
				customtitle = nodename
				nodename = nodename.rstrip('.')
				if nodename == '':
					nodename = node.id # keep as is, whatever
			
			if os.path.exists('data\\'+node.id): # must be a folder
				shutil.copytree('data\\'+node.id, output_dir+'\\'+nodename)
			else:
				os.mkdir(output_dir+'\\'+nodename)
			if customtitle or comment or source or icon:
				write_desktop_ini(output_dir+'\\'+nodename, customtitle, comment, source, icon)


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
