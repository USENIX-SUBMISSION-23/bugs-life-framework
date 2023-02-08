import os
import logging
from time import sleep
from bci.config import Config
from bci import cli

logger = logging.getLogger("bci")


class Jar:

    @staticmethod
    def do_automation(automation: str, browser: str, browser_version: str, browser_config: str, extension_path: str,
                      browser_binary: str, additional_cli_options: list, driver_exec: str, data_folder: str, mech_group: str,
                      custom=False, url_queue=None):
        if automation == "selenium":
            Jar.do_selenium_automation(automation, browser, browser_version, browser_config, extension_path,
                                       browser_binary, additional_cli_options, driver_exec, data_folder, mech_group,
                                       logger, custom=custom, url_queue=url_queue)
        elif automation == "terminal":
            Jar.do_terminal_automation(automation, browser, browser_version, browser_config, extension_path,
                                       browser_binary, additional_cli_options, driver_exec, data_folder, mech_group,
                                       logger, custom=custom, url_queue=url_queue)
        else:
            raise AttributeError("Unknown automation '%s'" % automation)

    @staticmethod
    def get_short_browser_version(version):
        return version.split('.')[0]

    @staticmethod
    def get_command(automation: str, browser: str, browser_version: str, browser_config: str, extension_path: str,
                    browser_binary: str, additional_cli_options: list, driver_exec: str, data_folder: str, mech_group: str,
                    custom=False, url_queue=None):
        short_browser_version = Jar.get_short_browser_version(browser_version)
        if browser == "chromium":
            browser = "chrome"
            command_addendum = " --arg --no-sandbox --arg --disable-gpu"
        else:
            command_addendum = ""

        command = "java -jar %s run %s %s leak --synced --local --browser-version %s --binary %s --data-folder %s" \
                  % (
                      os.path.basename(Config.evaluation_jar_path), browser, automation,
                      short_browser_version,
                      browser_binary, data_folder)
        if custom:
            command += " --custom -u %s" % " -u ".join(url_queue)

        command += command_addendum
        if driver_exec:
            command += " --driver-exec %s" % driver_exec
        if mech_group:
            command += " --mech-group %s" % mech_group
        if browser_config != "default":
            if browser_config == "btpc":
                command += " --block-3rd-party"
            elif browser_config == "pb":
                command += " --private-browsing"
            elif browser_config == "tp":
                command += " --tracking-protection"
            elif browser_config == "no-tp":
                command += " --no-tp"
            elif browser_config == "allow-java-applets":
                command += " --allow-java-applets"
            else:
                raise AttributeError("Browser config '%s' is not supported" % browser_config)

        if extension_path:
            command += " -e %s" % extension_path

        for cli_option in additional_cli_options:
            command += " --arg " + cli_option

        return command

    @staticmethod
    def do_selenium_automation(
            automation: str,
            browser: str,
            browser_version: str,
            browser_config: str,
            extension_path: str,
            browser_binary: str,
            additional_cli_options: list,
            driver_exec: str,
            data_folder: str,
            mech_group: str,
            logger,
            custom=False,
            url_queue=None):
        if driver_exec is None:
            raise AttributeError("Driver executable cannot be None for selenium automation")
        command = Jar.get_command(automation, browser, browser_version, browser_config, extension_path,
                                  browser_binary, additional_cli_options, driver_exec, data_folder, mech_group,
                                  custom=custom, url_queue=url_queue)
        short_browser_version = Jar.get_short_browser_version(browser_version)
        # Earlier chrome drivers do not respect the binary path argument
        # https://stackoverflow.com/a/48663064/3366464
        if browser == "chromium" and int(short_browser_version) < 60:
            # For these Chromium binaries, the --no-sandbox argument is unable to be passed through selenium for some reason.
            # For this reason, the docker image uses a proxy which automatically adds this argument.
            cli.execute("ln -sf %s /usr/bin/google-chrome-proxy" % browser_binary)

            if browser_config == "default" and not extension_path:
                cli.execute("cp /app/scripts/chromium/google-chrome-default /usr/bin/google-chrome")
            elif browser_config == "default" and extension_path:
                with open("/app/scripts/chromium/google-chrome-extension", 'r') as file:
                    script = file.read() % extension_path
                with open("/usr/bin/google-chrome", 'w') as file:
                    file.write(script)
            elif browser_config == "btpc":
                if extension_path:
                    raise AttributeError("Combining btpc with extension is not yet supported")
                if int(short_browser_version) <= 46:
                    cli.execute("cp /app/scripts/chromium/google-chrome-btpc-46 /usr/bin/google-chrome")
                else:
                    cli.execute("cp /app/scripts/chromium/google-chrome-btpc /usr/bin/google-chrome")
                    cli.execute("cp -rd /app/profiles/chromium/59_btpc /tmp/59_btpc")
                    # command += " --arg --user-data-dir=/tmp/59_btpc"

            cli.execute("chmod a+x /usr/bin/google-chrome")

        if browser == "firefox":
            if browser_config == "default":
                command += " --arg --profile=/app/profiles/firefox/default-67"
            elif browser_config == "btpc":
                command += " --arg --profile=/app/profiles/firefox/default-67"
            elif browser_config == "pb":
                command += " --arg --profile=/app/profiles/firefox/default-67"
            elif browser_config == "tp":
                command += " --arg --profile=/app/profiles/firefox/tp-67"

        # Execute evaluation command
        Jar.execute(command)

        if browser == "chromium":
            # Especially in the case of Chromium version < 60, the process won't be
            # killed effectively, so we have to do it manually to prevent a bottleneck
            cli.execute_and_return_status("pkill -f %s" % browser_binary)
            cli.execute_and_return_status("pkill -f %s" % driver_exec)
            cli.execute_and_return_status("pkill -f /usr/bin/google-chrome-proxy")

    @staticmethod
    def do_terminal_automation(
            automation: str,
            browser: str,
            browser_version: str,
            browser_config: str,
            extension_path: str,
            browser_binary: str,
            additional_cli_options: list,
            driver_exec: str,
            data_folder: str,
            mech_group: str,
            logger,
            custom=False,
            url_queue=None):
        command = Jar.get_command(automation, browser, browser_version, browser_config, extension_path,
                                  browser_binary, additional_cli_options, driver_exec, data_folder, mech_group,
                                  custom=custom, url_queue=url_queue)
        short_browser_version = Jar.get_short_browser_version(browser_version)
        profile_folder = Jar.increment_until_original("/tmp/new-profile")
        cli.execute("mkdir -p %s" % profile_folder)

        if browser == "chromium":
            command += " --arg --user-data-dir=%s" % profile_folder
            # TODO: This functionality should ultimately be transferred to the jar
            if browser_config == "default" and not extension_path:
                pass  # Jar takes care of this
            elif browser_config == "btpc" and not extension_path:
                if int(short_browser_version) < 17:
                    cli.execute("cp -r /app/profiles/chromium/6_btpc/Default %s" % profile_folder)
                elif int(short_browser_version) < 24:
                    cli.execute("cp -r /app/profiles/chromium/17_btpc/Default %s" % profile_folder)
                elif int(short_browser_version) < 36:
                    cli.execute("cp -r /app/profiles/chromium/24_btpc/Default %s" % profile_folder)
                elif int(short_browser_version) < 40:
                    cli.execute("cp -r /app/profiles/chromium/36_btpc/Default %s" % profile_folder)
                elif int(short_browser_version) < 46:
                    cli.execute("cp -r /app/profiles/chromium/40_btpc/Default %s" % profile_folder)
                elif int(short_browser_version) < 59:
                    cli.execute("cp -r /app/profiles/chromium/46_btpc/Default %s" % profile_folder)
                elif int(short_browser_version) < 86:
                    cli.execute("cp -r /app/profiles/chromium/59_btpc/Default %s" % profile_folder)
                else:
                    raise AttributeError("Chrome 86 and up not supported yet")
            elif browser_config == "pb":
                pass  # Jar takes care of this
            else:
                raise AttributeError("CLI automation currently does not support '%s' for chromium" % browser_config)

        if browser == "firefox":
            # Make Firefox trust the proxy CA and server CA
            cli.execute(
                "certutil -A -n littleproxy -t CT,c -i /app/ssl/LittleProxy_MITM.cer -d sql:%s" %
                profile_folder)  # cert9.db  key4.db  pkcs11.txt
            cli.execute("certutil -A -n littleproxy -t CT,c -i /app/ssl/LittleProxy_MITM.cer -d %s" %
                        profile_folder)  # Normally: cert8.db  key3.db  secmod.db, however: cert9.db  key4.db  pkcs11.txt

            cli.execute("certutil -A -n myCA -t CT,c -i /app/ssl/myCA.crt -d sql:%s" %
                        profile_folder)  # cert9.db  key4.db  pkcs11.txt
            # Normally: cert8.db  key3.db  secmod.db, however: cert9.db  key4.db  pkcs11.txt
            cli.execute("certutil -A -n myCA -t CT,c -i /app/ssl/myCA.crt -d %s" % profile_folder)

            # The certutil in the docker image refuses to create cert8.db, so we copy
            # an existing cert8.db which accepts the necessary CAs
            cli.execute("cp /app/profiles/firefox/cert8.db %s" % profile_folder)

            command += " --arg --profile=%s" % profile_folder
            if browser_config == "default" and not extension_path:
                pass  # Jar takes care of this
            elif browser_config == "btpc" and not extension_path:
                pass  # Jar takes care of this
            elif browser_config == "tp":
                pass  # Jar takes care of this
            elif browser_config == "no-tp":
                pass  # Jar takes care of this
            elif browser_config == "pb" and not extension_path:
                pass  # Jar takes care of this
            elif browser_config == "allow-java-applets" and not extension_path:
                pass  # Jar takes care of this
            else:
                raise AttributeError("CLI automation currently does not support '%s' for firefox" % browser_config)

        command += " --visits 3 --sessions 1"

        Jar.execute(command)
        sleep(2)

        # Remove new profile if CLI automation
        cli.execute_and_return_status("rm -rd %s" % profile_folder)
        cli.execute_and_return_status("rm -rd %s" % profile_folder)
        cli.execute_and_return_status("rm -rd %s" % profile_folder)

    @staticmethod
    def execute(command: str):
        logger.info(f"Command: {command}")
        timeout = 30
        max_tries = 3
        finished_within_retries = cli.execute(command,
                                              cwd=os.path.expanduser(os.path.dirname(Config.evaluation_jar_path)),
                                              timeout=timeout, max_tries=max_tries)
        if not finished_within_retries:
            logger.error(f"Command did not finish within the given timeout '{timeout}' and max number of tries '{max_tries}", exc_info=True)

    @staticmethod
    def increment_until_original(path: str):
        if not os.path.exists(path):
            return path
        i = 0
        while True:
            new_path = path + str(i)
            if not os.path.exists(new_path):
                return new_path
            i += 1
