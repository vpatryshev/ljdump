# ljdump # 

## A Livejournal or Dreamwidth archive tool ##

This program reads the journal entries from a Livejournal or Dreamwidth (or compatible) blog site and archives them in a subdirectory named after the journal name.  First it places all the data in a SQLite database, then it uses that to generate browseable HTML pages:

* One page per entry, with comments shown in their original threaded structure.
* History pages with 20 entries each, ordered by date, for as many pages as needed.
* A table of contents page with links to the above, and to entries organized by tag.

Page structure is as close as possible to what Dreamwidth renders, so you can drop in your own stylesheet and the result will look a lot like your own journal.

The script keeps track of where it left off the last time it was run, so the next time you run it, it will only fetch the entries and comments that have changed.

<img src="treasure.jpg" style="max-width:25%;float:right;padding-left:0.7em;">

### An image cache ###

I put a lot of my photos and pixel art in my journal, and an archive would be kind of lame without them.  That's why this script can also attempt to store local copies of the images embedded in journal entries.  It organizes them by month in an images folder next to all the HTML.

This is an optional step, and it's off by default.  To run it you need to use the `--cache_images` argument when you invoke the script.

Every time you run it, it will attempt to cache 200 more images, going from oldest to newest.  It will skip over images it's already tried and failed to fetch, until 24 hours have gone by, then it will try those images once again.

The image links in your entries are left unchanged in the database.  They're swapped for local links only in the generated HTML pages.

### Limitations ###

This script uses the XML-RPC API to communicate with Livejournal and its descendents.  There is some information that is just not available using this protocol, such as:

* Full names of journals
* Theme information for moods
* The specific icons set by commenters in their comments

So, it's not possible to get the local HTML to look exactly like your online journal.

## How to use ##

__To get the full archive of a very large journal, you may need to run the script multiple times, until it says there are no new changes.__  Take note of the `--max` command line argument (described below) which can be used to speed this up.

### Windows ###

If you don't have Python 3 installed, [download it from here](https://www.python.org/downloads/).  All the default settings are fine when you run the installer.

Next, download ljdump [from the releases page](https://github.com/GBirkel/ljdump/releases/).  (Go for the zipfile in the "Assets" section.)  Open up the zip file on your machine and drag everything out into a new folder.  Then, the simplest way to go is to double-click `scripts/ljdump.py`, which will open a terminal window.

If you want to use the image caching feature, you'll need to launch the terminal window first.  Try right-clicking in the folder where you dragged the ljdump files, and choosing "Open in Terminal".  A terminal window should open that's already pointed to that directory.  Enter the following:

`./scripts/ljdump.py --cache_images`

### MacOS ###

Download ljdump [from the releases page](https://github.com/GBirkel/ljdump/releases/).  (Go for the zipfile in the "Assets" section.)  If the zipfile isn't automatically decompressed into a folder, double-click on it.

Launch the Terminal app, either by typing it into Spotlight or going to the Utilities folder in Applications and opening it from there.  In the Terminal window that appears, type `cd ` (without pressing "return" yet) and then go back to your Finder window.  Drag the decompressed ljdump folder into the Terminal window.  The location of the folder in the filesystem will appear after your `cd ` command.  Press "return." The Terminal window is now pointing at that folder.

Enter `./scripts/ljdump.py` (or `./scripts/ljdump.py --cache_images` if you want to cache images) and hit "return."

At this point, if you haven't ever run a Python 3 script before on your machine, a window may pop up from Apple saying you need to install the developer tools, like so:

<img src="dev_tools_alert.png" style="width:50%;max-width:600px;">

This is normal.  Just let it download and install, and then try running the command again.  (In the Terminal window, tap the "up" arrow once, and you'll see the previous command you entered.  Then hit "return" again.)

The script will prompt you for a location to download from.  Accept the default for Livejournal by pressing "return", or enter another location, for example `https://dreamwidth.org` for Dreamwidth.  Then the script will ask for your journal username and password, and begin downloading all your journal entries, comments, and userpics.

You may optionally download entries from a different journal (a community) where you are a member. If you are a community maintainer, you can also download comments from the community.

## Using the configuration file ##

If you want to save your username and password so you don't have to type it every time you run ljdump, you can save it in the configuration file.

The configuration is read from "ljdump.config". A sample configuration is provided in "ljdump.config.sample", which should be copied and then edited.

The configuration settings are:

* __server__ - The XMLRPC server URL.

  This should only need to be changed if you are dumping a journal that is livejournal-compatible but is not livejournal itself.

* __username__ - The livejournal user name.

  A subdirectory will be created with this same name to store the journal entries.

* __password__ - The account password.

  This password is sent in the clear, so if you specify an alternative server, ensure you use a URL starting with https:// so the connection is encrypted. If not provided here, will prompt for it when run.

* __journal__ - Optional: The journal to download entries from.

  If this is not specified, the "username" journal is downloaded. If this is specified, then only the named journals will be downloaded.  This element may be specified more than once to download multiple journals.

### Command line options ###

`--quiet`

Makes the script print a lot less status information to the console as it runs.

`--no_html`

By defualt, this script constructs HTML pages after saving everything to the SQLite database.  This flag skips the HTML.

`--max n`

Fetch a maximum of n entries and comments that are new since the last sync, then stop.  The default is 400, but can be set lower if you want to run a test, or higher if you want to download your whole journal at once and are confident the server won't complain.  I recommend using the default at least once, then using a value of 1500 afterward until you're caught up.

`--cache_images`

Activates the image caching.  The script will attempt to cache 200 images at a time.  If it fails to cache an image it will skip it for 24 hours, even if the script is run again during that time.

`--dont_retry_images`

If image caching is on, this option will prevent the script from re-trying any images it's failed to cache, though it will still try and cache images it hasn't seen before, like in new or edited entries.

Note that you can run the script that generates the HTML by itself, skipping over the synchronization process.  Running it repeatedly will let you cache lots of images without bothering the journal servers:

`./scripts/ljdumptohtml.py --cache_images`

## Fetching a journal with `dwscrape.py`

`dwscrape.py` fetches a journal into the ljdump database format and lets you
pick *how*, with `--method` (default `sync`):

* `sync` — ljdump's XML-RPC incremental sync (your own journal; only fetches
  what changed since the last run; needs `--username`/`--password`). This is the
  same engine as `ljdump.py`.
* `scrape` — HTTP pagination scraping (works for other people's public journals,
  which the XML-RPC sync can't reach).
* `archive` — HTTP archive-page crawl; more reliable than plain pagination.

```bash
# Incremental sync of your own journal (default)
scripts/dwscrape.py juan_gandhi --username juan_gandhi --password PASSWORD

# Scrape someone else's public journal over HTTP
scripts/dwscrape.py kdanilov --method scrape
scripts/dwscrape.py kdanilov --method archive

# Credentials may also come from a config file
scripts/dwscrape.py kdanilov --config ./juan_gandhi.config --method archive
```

(`--use-archive` is still accepted as a deprecated alias for `--method archive`.)

By default `scrape` fetches the **whole** journal (no entry limit), skipping any
entries already stored in the database, so re-running it backfills without
re-scraping what you have. Options:

* `--max N` — stop after N new entries (default: no limit).
* `--incremental` — stop as soon as several consecutive listing pages are all
  already in the database (fast routine updates once the journal is fully
  archived; may miss older, not-yet-scraped entries, so use a full run first).

```bash
# Full scrape of a large journal (gets everything, skipping duplicates)
scripts/dwscrape.py taki-net --method scrape --user USER --password PASS

# Quick update once already archived
scripts/dwscrape.py taki-net --method scrape --incremental --user USER --password PASS
```


## Posting and editing entries

Besides archiving, this project can push entries *back* to Dreamwidth over
XML-RPC. The shared library `blog.py` exposes a `Blog` class with two methods:

* `Blog.post(subject, body, tags, security, post_date)` → creates a new entry
  (`LJ.XMLRPC.postevent`).
* `Blog.edit(itemid, subject, body, tags, security, post_date)` → overwrites an
  existing entry, identified by its server-side `itemid` (`LJ.XMLRPC.editevent`).

Both authenticate with `auth_method="clear"` (plain username/password), so use
an `https://` server URL. `security` is one of `public`, `friends`, `private`;
passing a `post_date` posts the entry back-dated.

### Post a text file — `post.py`

The first line of the file is the subject, the rest is the body.

```bash
python scripts/post.py path/to/entry.txt \
  --user USERNAME --password PASSWORD \
  [--tags "tag1, tag2"] [--security public|friends|private] \
  [--date 2021-11-17T09:19:00+00:00]
```

### Post entries from a database — `post_from_db.py`

Reads rows from a journal database under `work/` and posts them. Note that
`--db` is resolved relative to the `work/` directory (e.g. `--db
juan_gandhi/journal.db` reads `work/juan_gandhi/journal.db`).

```bash
# A single entry by itemid:
python scripts/post_from_db.py --user USERNAME --password PASSWORD \
  --db juan_gandhi/journal.db --itemid 4066 [--server https://www.dreamwidth.org] \
  [--security public|friends|private] [--dry-run]

# Or a batch, by SQL WHERE clause against the entries table:
python scripts/post_from_db.py --user USERNAME --password PASSWORD \
  --db juan_gandhi/journal.db --where "eventtime LIKE '2009-06%'"
```

Exactly one of `--itemid` or `--where` is required. The script throttles between
posts and prints the resulting URL for each. `--dry-run` lists the matched
entries without posting. Entries are posted back-dated to their original
`eventtime`.

### Update existing entries — `update_from_db.py`

Overwrites **existing** server entries with the content of database rows, via
`editevent`. Choose the entries to update with either `--itemid` (a single
itemid or a comma-separated list) or `--where` (a SQL WHERE clause against the
entries table, which is resolved to the list of matching itemids). By default
the entry edited on the server is the one with the same itemid as the database
row; use `--target-itemid` (single `--itemid` only) to point at a different
server-side entry (e.g. one created fresh by `post_from_db.py` and assigned a
new id by the server). As with `post_from_db.py`, `--db` is resolved relative to
`work/`.

```bash
# By explicit itemid(s):
python scripts/update_from_db.py --user USERNAME --password PASSWORD \
  --db juan_gandhi/journal.db --itemid 4066[,4067,...] \
  [--target-itemid 67890] [--server https://www.dreamwidth.org] \
  [--security public|friends|private] [--dry-run]

# By SQL WHERE clause (updates every matching entry):
python scripts/update_from_db.py --user USERNAME --password PASSWORD \
  --db juan_gandhi/journal.db --where "props_taglist LIKE '%music%'" [--dry-run]
```

Exactly one of `--itemid` or `--where` is required (and `--target-itemid` only
applies to a single `--itemid`). The selected entries are updated in turn
(throttled between them); an itemid that isn't in the database is reported and
skipped. `--dry-run` prints the database itemid and the server itemid that
*would* be edited for each, so you can confirm before running it live. On success
each prints `OK` and the entry's URL. The building blocks are also exposed for
use from other scripts: `select_itemids(db, where)` and
`update_one(db, account, itemid, target_itemid=None, security="public", dry_run=False)`.

### Compare a stored entry with the live version — `compare_from_db.py`

Fetches an entry from the server and compares its content (subject, tags, body)
against the copy stored in the database. If they match it says so; if not, it
prints a single unified diff (standard `---`/`+++`/`@@` format, with context),
so only the changed regions show even for long entries. When writing to a
terminal it highlights the differing characters in color — database in blue,
online in red — so you can spot exactly what changed within a line. Line-ending
differences are ignored. As with the scripts above, `--db` is resolved relative
to `work/`.

```bash
python scripts/compare_from_db.py --user USERNAME --password PASSWORD \
  --db juan_gandhi/journal.db --itemid 4066 \
  [--server https://www.dreamwidth.org] [--journal community] \
  [--color auto|always|never]
```

`--color` defaults to `auto` (color when stdout is a terminal); use `always` to
keep color when piping, or `never` to disable it. Exit status is diff-style:
`0` if identical, `1` if they differ, `2` if the entry is missing on either
side. The comparison logic is also exposed as
`compare_entry(db, account, itemid, journal=None, color=False)` for use from
other scripts; it returns a result dict (`in_db`, `online`, `identical`,
`differences`, `report`).


## Have fun!  ##

You should know that there's no warranty here, and no guarantee that Dreamwidth or Livejournal won't shut off their XML-RPC protocol at some point.  Try not to aggravate them by downloading your journal a thousand times, mmmkay?

A Livejournal [community](https://ljdump.livejournal.com) was set up for questions or comments on the original version of this script back in 2009, but it has not seen attention for years.  Say [hello to me here](https://garote.dreamwidth.org/330489.html) if you have feedback.

