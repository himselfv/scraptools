# Scrapbook tools #

Python scripts to service Scrapbook X repositories. Scrapbook / Scrapbook X is a Firefox note-taking and web page capturing plugin.

Currently a single tool:


### convert.py

Converts a Scrapbook X repository to a file/folder tree.

* Folders are converted to folders

* Plain notes are converted to text files.

* Enhanced notes and saved web pages are converted to MHT files or individual folders.

Also generates directory index files which contain information which could not have been represented natively in the file system:

* Alternative file ordering

* Weird file names


### Howto

This is a python script, you need Python 2.7 to run it. Install it, have it in PATH. It uses rdflib and lxml, run `pip install rdflib lxml` from admin command line once you have Python.


Usage: 
```
convert.py --from [path to Scrapbook data] --convert [where to place files] --mht
```

Path to Scrapbook data is usually something like `C:\Users\Your username\AppData\Roaming\Mozilla\Firefox\[Your Firefox profile]\Scrapbook`. Since it's your data, I'd backup it before doing anything, just in case.

Output path is a folder which will be created, populated with converted data.

By default web pages are saved as HTML with resources in their own folders, use `--mht` to turn them into single .mht files instead.


### License

Licensed under the [MIT License](LICENSE.txt).