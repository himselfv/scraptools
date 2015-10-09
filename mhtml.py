import os
import base64
import email, email.message
import mimetypes
import codecs
import quopri
import sys
import argparse

# Based on https://github.com/Modified/MHTifier/blob/master/mhtifier.py


# Returns MHT (email.message) built from folder data
def mht_object(folder):
	# Create archive as multipart message.
	a = email.message.Message()
	a["MIME-Version"] = "1.0"
	a.add_header("Content-Type", "multipart/related", type="text/html")

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

#			if t and t.startswith("text/"):
#				m["Content-Transfer-Encoding"] = "quoted-printable"
#				payl = codecs.open(p, "rt").read()
#				print payl
#				m.set_payload(quopri.encodestring(payl.encode("utf-8")).decode("ascii")) #??? WTF?
#			else:
				m["Content-Transfer-Encoding"] = "base64"
				m.set_payload(base64.b64encode(open(p, "rb").read()).decode("ascii"))

			# Only set charset for index.html to UTF-8, and no location.
			if f == "index.html":
				m.add_header("Content-Type", "text/html", charset="utf-8")
				#??? m.set_charset("utf-8")
			else:
				m["Content-Location"] = p
			a.attach(m)
	return a


# Returns MHT data as binary
def mht_bytes(folder):
	mht = mht_object(folder)
	return mht.as_string(unixfrom=False).encode("utf-8")

# Writes MHT to a target file. Returns data size
def mht_pack(folder, filename):
	mht = open(filename, "wb")
	data = mht_bytes(folder)
	mht.write(data) # Not an mbox file, so we don't need to mangle "From " lines, I guess?
	mht.close()
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

	# New directory?
	if args.unpack:
		os.mkdir(args.dir)

	if args.pack:
		if args.mht == "-":
			mht = sys.stdout
		else:
			if os.path.exists(args.mht) and not args.overwrite:
				sys.stderr.write("Error: MHT file exists, won't overwrite.\n")
				return -2
			mht = open(args.mht, "wb")
		if not args.quiet:
			sys.stderr.write("Packing...\n")
		mht.write(mht_bytes(args.dir))
		mht.close()
		if not args.quiet:
			sys.stderr.write("Done.")


if __name__ == "__main__":
	sys.exit(main())