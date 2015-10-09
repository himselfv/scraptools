"""
MHTML format handling.
Based on https://github.com/Modified/MHTifier/blob/master/mhtifier.py
Usage:
	mht = mhtml()
	mht.from_folder(folder)
	mht.save_to_file(filename)

From command line:
	mhtml --pack mht folder
"""
import os
import base64
import email, email.message
import mimetypes
import codecs
import quopri
import sys
import argparse


class MHTML(object):
	def __init__(self):
		self.content = None
		pass
	
	@property
	def payload_count():
		if content is None:
			return 0
		else:
			return len(content.get_payload())
	
	def from_folder(self, folder):
		"""
		Initializes MHTML object with the contents of the specified folder.
		At this point it's impossible to add several folders.
		"""
		# Create archive as multipart message.
		self.content = email.message.Message()
		self.content["MIME-Version"] = "1.0"
		self.content.add_header("Content-Type", "multipart/related", type="text/html")

		# Walk current directory.
		for (root, _, files) in os.walk(folder):
			# Create message part from each file and attach them to archive.
			for f in files:
				p = os.path.join(root, f).lstrip("./")
				m = email.message.Message()
				# Encode and set type of part.
				t = mimetypes.guess_type(f)[0]
				if t:
					m["Content-Type"] = t

				# At this point nothing is encodede as quoted-printable
				# because we can't tell the source encoding => can't load (defaults to ASCII) to recode
				#if t and t.startswith("text/"):
				#	m["Content-Transfer-Encoding"] = "quoted-printable"
				#	payl = codecs.open(p, "rt").read()
				#	m.set_payload(quopri.encodestring(payl.encode("utf-8")).decode("ascii")) #??? WTF?
				#else:
					m["Content-Transfer-Encoding"] = "base64"
					m.set_payload(base64.b64encode(open(p, "rb").read()).decode("ascii"))

				# Only set charset for index.html to UTF-8, and no location.
				if f == "index.html":
					m.add_header("Content-Type", "text/html", charset="utf-8")
					#??? m.set_charset("utf-8")
				else:
					m["Content-Location"] = p
				self.content.attach(m)
	
	def to_folder(self, folder, overwrite = False):
		"""
		Stores the contents of MHT as files in the specified folder.
		overwrite: without this, existing files will stop the operation.
		"""
		for p in content.get_payload(): # walk() for a tree, but I'm guessing MHT is never nested?
			#??? cs = p.get_charset() # Expecting "utf-8" for root HTML, None for all other parts.
			ct = p.get_content_type() # String coerced to lower case of the form maintype/subtype, else get_default_type().
			fp = p.get("content-location") or "index.html" # File path. Expecting root HTML is only part with no location.

			# Create directories as necessary.
			if os.path.dirname(fp):
				os.makedirs(os.path.dirname(fp), exist_ok=True)

			# Save part's body to a file.
			open(fp, "wb").write(p.get_payload(decode=True))
		
	
	def from_bytes(self, bytes):
		"""
		Loads MHT data from binary representation
		"""
		self.content = email.message_from_bytes(bytes)
	
	def to_bytes(self):
		"""
		Returns MHT data as binary
		"""
		return self.content.as_string(unixfrom=False).encode("utf-8")
	
	def load_from_file(self, filename):
		"""
		Loads MHT from a packed file.
		"""
		f = open(filename, "rb")
		self.from_bytes(f.read())
		f.close()
	
	def save_to_file(self, filename):
		"""
		Writes MHT to a target file. Returns data size.
		"""
		f = open(filename, "wb")
		data = self.to_bytes()
		f.write(data) # Not an mbox file, so we don't need to mangle "From " lines, I guess?
		f.close()
		return len(data)





# Can be called manually for testing
def main():
	parser = argparse.ArgumentParser(description="Extract MHT archive into new directory.")
	parser.add_argument("mht", help='path to MHT file, use "-" for stdin/stdout.')
	parser.add_argument("dir", help="directory to create to store parts in, or read them from.")
	parser.add_argument("-p", "--pack", action="store_true", help="pack file under DIR into an MHT.")
	parser.add_argument("-u", "--unpack", action="store_true", help="unpack MHT into a new DIR.")
	parser.add_argument("-ow", "--overwrite", action="store_true", help="overwrite existing files (MHT or in target dir)")
	parser.add_argument("-v", "--verbose", action="store_true")
	parser.add_argument("-q", "--quiet", action="store_true")
	args = parser.parse_args()

	if args.pack == args.unpack:
		sys.stderr.write("Invalid: must specify one action, either --pack or --unpack.\n")
		return -1

	if args.unpack:
		if args.mht == "-":
			inp = sys.stdin.buffer
		else:
			inp = open(args.mht, "rb")

		if not args.quiet:
			sys.stderr.write("Unpacking...\n")

		# New directory?
		os.mkdir(args.dir)
		
		# Change directory so paths (content-location) are relative to index.html.
		oldcwd = os.getcwd()
		os.chdir(args.dir)
		
		mht = MHTML()
		mht.from_bytes(inp.read())
		mht.to_folder(args.dir)
		
		inp.close()
		os.chdir(oldcwd)

	if args.pack:
		if args.mht == "-":
			outp = sys.stdout
		else:
			if os.path.exists(args.mht) and not args.overwrite:
				sys.stderr.write("Error: MHT file exists, won't overwrite.\n")
				return -2
			outp = open(args.mht, "wb")
		if not args.quiet:
			sys.stderr.write("Packing...\n")
		mht = MHTML()
		mht.from_folder(args.dir)
		outp.write(mht.to_bytes())
		outp.close()

	if not args.quiet:
		sys.stderr.write("Done.")

if __name__ == "__main__":
	sys.exit(main())