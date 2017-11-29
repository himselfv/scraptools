# Scrapbook tools #

Python scripts to service Scrapbook X repositories. Scrapbook / Scrapbook X is a Firefox note-taking and web page capturing plugin.

Currently a single tool:


### convert.py

Converts a Scrapbook X repository to a file/folder tree.

* Folders are converted to folders

* Plain notes are converted to text files.

* Web pages are converted to MHT files or individual folders.

Also generates directory index files which contain information which could not have been represented natively in the file system:

* Alternate file ordering

* Weird file names
