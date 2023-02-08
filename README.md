# IMPORTANT: To remain anonymous, all potentially identifying files have been removed! In this state, the framework is not fully functional!

### Setup instructions

#### 1. Clone this repository.


#### 2. Install `docker`, `docker-compose` and `mercurial`.


#### 3. Setup a MongoDB instance and add the following information to `/etc/environment`. Restart afterwards.

```
bci_mongo_host=[ip_address_of_host]
bci_mongo_database=[database_name]
bci_mongo_username=[database_user]
bci_mongo_password=[database_password]
```

*Tip: if the Docker address pool interferes with `ip_address_of_host`, modify `/etc/docker/daemon.json` (e.g. `{"default-address-pools":[
{"base":"192.168.0.0/16","size":24}]}`).*


#### 4. Fetch the necessary helper files.

* Clone the Chromium and Firefox repositories to the `./browser-repos` folder (this can take a while).

```bash
# Cloning the Firefox mercurial release repository.
cd [projectRoot]/browser-repos
hg clone https://hg.mozilla.org/releases/mozilla-release/ firefox-release

# Since the Chromium git repository is huge, we'll have to clone it in multiple steps [source: https://stackoverflow.com/a/22317479/3366464].
cd [projectRoot]/browser-repos
mkdir chromium && cd chromium
g clone --depth 1 https://chromium.googlesource.com/chromium/src.git
cd src
git fetch --unshallow
git pull --all
```

* Browser drivers (if using Selenium).


#### 5. Build the docker image:

This step should be repeated when source-code modifications should be propagated to the docker image.

```bash
sudo docker-compose build
```


#### 6. Start the required docker containers:

```bash
sudo docker-compose up -d bci web
```


#### 7. Visit the web interface at `http://localhost:5000/eval/custom/CSP/chromium` or `http://localhost:5000/eval/custom/CSP/firefox` with your web browser.


### Interesting links

* [Chromium Main Console](https://ci.chromium.org/p/chromium/g/main/console)
* [OmahaProxy](https://omahaproxy.appspot.com/)
* [Explanation to get certain Chromium version](https://www.chromium.org/getting-involved/download-chromium)
* [Chromium Browser Snapshots](https://commondatastorage.googleapis.com/chromium-browser-snapshots/index.html)
* [Chromium Continuous Builds](https://commondatastorage.googleapis.com/chromium-browser-continuous/index.html)
* [cr-rev](https://cr-rev.appspot.com/)
* [Building old Chromium revisions](https://chromium.googlesource.com/chromium/src.git/+/master/docs/building_old_revisions.md)
* [Meta-data of nightly releases](https://hg.mozilla.org/mozilla-central/json-firefoxreleases)
* [No Chrome sandboxing in container environment](https://stackoverflow.com/questions/59087200/google-chrome-failed-to-move-to-new-namespace)

* [Info on Firefox development cycle](https://mozilla.github.io/process-releases/draft/development_overview/)