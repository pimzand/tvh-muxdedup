tvh-muxdedup
=================================
Tvheadend mux deduplication script, written in the python language, using the Tvheadend API


Background
----------

TVHeadend creates a new mux whenever it determines that an existing mux is not correct.
This will cause duplicate muxes, along with duplicate services.
Manually deleting duplicate muxes is a lot of work, and it comes with a dilemma.
Deleting the most recently created will result in this mux coming back at the next scan.
Deleting the older mux of a duplicate pair may result in losing channel mappings.
 
This script is there to automate removal of as many duplicate muxes as possible.
For each pair of duplicate muxes, it will assume the most recently created is the best one.
If the older one has no channel mappings, it will delete the older one.
If the older one has channel mappings, it will copy the differing parameters of the new mux to the old one.
After that, it will delete the new one.
If the new mux appears to be bad, it will delete the new one.
The script tries to never delete a mux that has services mapped to channels.

The script is limited to DVB-S muxes, as I have never seen duplicate DVB-C or DVB-T muxes.



Environment variables
---------------------

Name          | Description
--------------|--------------------------------------------
TVH_URL_API   | URL like http://localhost:9981/api
TVH_USER      | username for HTTP API
TVH_PASS      | password for HTTP API


Usage
-------------

Without any arguments, the script will run in dry mode.
It will list all your duplicate muxes side by side, and describes what it would do.
Run with argument '--no-dry-run' to actually make changes to your Tvheadend database.

Be wary, the script works for me, but it may destroy your database.
Consider making a backup of your Tvheadend database before trying.


Examples:
---------

`TVH_USER=admin TVH_PASS=admin ./tvh-muxdedup.py`

`TVH_USER=admin TVH_PASS=admin ./tvh-muxdedup.py --no-dry-run`
