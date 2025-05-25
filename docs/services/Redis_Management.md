# Redis Management in Grazr

This document provides a detailed overview of how the Redis in-memory data store is bundled, configured, and managed within the Grazr application. It's intended for contributors who want to understand or work on Redis-related functionalities.

## Table of Contents

1.  [Overview of Redis in Grazr](#overview-of-redis-in-grazr)
2.  [Redis Bundling (`bundle_redis.sh`)](#redis-bundling-bundle_redissh)
    * [Script Purpose](#script-purpose)
    * [Key Steps in Bundling](#key-steps-in-bundling)
        * [Version Specification](#version-specification)
        * [Dependencies](#dependencies)
        * [Downloading Source](#downloading-source)
        * [Compilation](#compilation)
    * [Bundle Output Structure](#bundle-output-structure)
3.  [Configuration (`config.py` for Redis)](#configuration-configpy-for-redis)
    * [Entry in `AVAILABLE_BUNDLED_SERVICES`](#entry-in-available_bundled_services)
    * [Path Constants](#path-constants)
4.  [Redis Manager (`redis_manager.py`)](#redis-manager-redis_managerpy)
    * [Core Responsibilities](#core-responsibilities)
    * [Configuration Setup (`_ensure_redis_config`)](#configuration-setup-_ensure_redis_config)
        * `redis.conf`
    * [Process Control (`start_redis`, `stop_redis`)](#process-control-start_redis-stop_redis)
    * [Status Checking (`get_redis_status`)](#status-checking-get_redis_status)
    * [Version Retrieval (`get_redis_version`)](#version-retrieval-get_redis_version)
5.  [Interaction with Other Components](#interaction-with-other-components)
6.  [Troubleshooting Redis](#troubleshooting-redis)
7.  [Contributing to Redis Management](#contributing-to-redis-management)

## 1. Overview of Redis in Grazr

Grazr includes a bundled Redis server to provide a fast in-memory key-value store, commonly used for caching, session management, and real-time data. Grazr manages a single instance of this bundled Redis server.

## 2. Redis Bundling (`bundle_redis.sh`)

The `packaging/bundling/bundle_redis.sh` script is responsible for fetching the Redis source, compiling it, and placing the necessary binaries into Grazr's bundle structure.

### Script Purpose

* Automates the download of Redis source code for a specified version.
* Compiles Redis from source.
* Installs the compiled `redis-server` and `redis-cli` binaries into the designated bundle directory for Redis within Grazr (`~/.local/share/grazr/bundles/redis/bin/`).

### Key Steps in Bundling

#### Version Specification
The script allows specifying a Redis version (e.g., "7.2.4") or defaults to a recent stable version. The version string is used to construct the download URL.

#### Dependencies
Compiling Redis from source typically requires:
* `gcc` (C compiler)
* `make`
* `tcl` (for running tests, though not strictly necessary for just building the server/CLI)
The script includes a prerequisite check for `make` and `gcc`.

#### Downloading Source
The script downloads the Redis source tarball (e.g., `redis-7.2.4.tar.gz`) from the official Redis download site: `http://download.redis.io/releases/`.

#### Compilation
* The script extracts the source code into a temporary directory.
* It then navigates into the source directory and runs `make MALLOC=libc -j$(nproc)`.
    * `MALLOC=libc`: This tells Redis to compile against the standard C library's malloc implementation, avoiding a dependency on `jemalloc` which might not be present on all systems and simplifies bundling.
    * Redis does not usually require a `./configure` step for basic compilation.
* After successful compilation, the `redis-server` and `redis-cli` binaries are available in the `src` subdirectory of the Redis source tree.

### Bundle Output Structure
A successful run of `bundle_redis.sh` places the binaries as follows:
```
~/.local/share/grazr/bundles/redis/
└── bin/
    ├── redis-server  (the executable server binary)
    └── redis-cli     (the executable command-line interface)
```

## 3. Configuration (`config.py` for Redis)

The `grazr/core/config.py` file defines paths and constants related to the bundled Redis service.

### Entry in `AVAILABLE_BUNDLED_SERVICES`
```python
    "redis": {
        "display_name": "Redis",
        "category": "Cache & Queue",
        "process_id": "internal-redis", # Fixed ID for the single instance
        "default_port": 6379,
        "version_args": ["--version"], # For redis-server
        "version_regex": r'v=([0-9\.]+)', # Example: Redis server v=7.2.4 ...
        "binary_path_constant": "REDIS_BINARY", # Points to the redis-server executable
        "manager_module": "redis_manager",
        "doc_url": "https://redis.io/docs/",
        "log_path_constant": "INTERNAL_REDIS_LOG",
        "pid_file_constant": "INTERNAL_REDIS_PID_FILE",
        # ...
    },
```

### Path Constants
`config.py` defines specific paths for the Redis bundle, active configuration, and runtime files:
```python
REDIS_BUNDLES_DIR = BUNDLES_DIR / 'redis'
REDIS_BINARY = REDIS_BUNDLES_DIR / 'bin/redis-server'
REDIS_CLI_BINARY = REDIS_BUNDLES_DIR / 'bin/redis-cli'

INTERNAL_REDIS_CONF_DIR = CONFIG_DIR / 'redis'
INTERNAL_REDIS_CONF_FILE = INTERNAL_REDIS_CONF_DIR / 'redis.conf'
INTERNAL_REDIS_DATA_DIR = DATA_DIR / 'redis_data' # For RDB/AOF persistence
INTERNAL_REDIS_PID_FILE = RUN_DIR / "redis.pid"
INTERNAL_REDIS_LOG = LOG_DIR / 'redis.log'
```

## 4. Redis Manager (`redis_manager.py`)

The `grazr/managers/redis_manager.py` module contains the logic for managing the bundled Redis service.

### Core Responsibilities
* Ensuring the active configuration directory (`~/.config/grazr/redis/`) and data directory (`~/.local/share/grazr/redis_data/`) exist.
* Creating a default `redis.conf` configuration file tailored for Grazr.
* Starting and stopping the `redis-server` process using `process_manager.py`.
* Checking the status and version of the running Redis server.

### Configuration Setup (`_ensure_redis_config`)
* **`redis.conf`:**
    * This function creates `~/.config/grazr/redis/redis.conf`.
    * It populates this file with essential settings for a local development Redis instance:
        * `port {configured_port}` (from `services.json`, defaults to `config.REDIS_DEFAULT_PORT` 6379)
        * `pidfile /path/to/grazr_run_dir/redis.pid` (points to `config.INTERNAL_REDIS_PID_FILE`)
        * `logfile /path/to/grazr_log_dir/redis.log` (points to `config.INTERNAL_REDIS_LOG`)
        * `dir /path/to/grazr_data_dir/redis_data` (points to `config.INTERNAL_REDIS_DATA_DIR` for RDB/AOF files)
        * `bind 127.0.0.1 ::1` (listen on loopback interfaces only)
        * `daemonize no` (Grazr's `process_manager.py` handles daemonization/backgrounding)
        * Other sensible defaults for local use (e.g., basic persistence settings).

### Process Control (`start_redis`, `stop_redis`)
* **`start_redis()`:**
    1.  Calls `_ensure_redis_config()` to prepare the configuration file.
    2.  Constructs the command to start `redis-server`:
        ```bash
        /path/to/bundle/bin/redis-server /path/to/active/redis.conf
        ```
    3.  Calls `process_manager.start_process()` with:
        * `process_id = config.REDIS_PROCESS_ID` ("internal-redis")
        * The command.
        * `pid_file_path = config.INTERNAL_REDIS_PID_FILE`
        * `log_file_path = config.INTERNAL_REDIS_LOG` (note: Redis also logs to its own file as per `redis.conf`)
* **`stop_redis()`:**
    * Calls `process_manager.stop_process(config.REDIS_PROCESS_ID)`. Redis handles `SIGTERM` (default from `stop_process`) gracefully by performing a save if persistence is enabled.

### Status Checking (`get_redis_status`)
* Relies on `process_manager.get_process_status(config.REDIS_PROCESS_ID)`, which checks the PID file specified in `redis.conf` and managed by `redis-server`.
* Can also attempt a connection using `redis-cli ping` as a secondary liveness check.

### Version Retrieval (`get_redis_version`)
* Runs `/path/to/bundle/bin/redis-server --version`.
* Parses the output using the regex from `config.AVAILABLE_BUNDLED_SERVICES["redis"]["version_regex"]` (e.g., `r'v=([0-9\.]+)'`).

## 5. Interaction with Other Components

* **`services_config_manager.py`**: Stores the user's configured Redis instance details (port, autostart flag, name) in `services.json` with `service_type: "redis"`.
* **`worker.py`**: Handles `start_redis` and `stop_redis` tasks, calling the respective functions in `redis_manager.py`.
* **`ServicesPage.py` & `AddServiceDialog.py`**: Allow the user to add (configure port) and manage the Redis service.

## 6. Troubleshooting Redis

* **Fails to Start:**
    * **Log File:** Check `~/.config/grazr/logs/redis.log` for error messages from Redis itself.
    * **Port Conflict:** Ensure the configured port (default 6379) is not already in use: `sudo ss -tulnp | grep ':6379'`.
    * **Permissions:** The user running Grazr must have write access to `config.INTERNAL_REDIS_DATA_DIR` and the directory containing `config.INTERNAL_REDIS_LOG` and `config.INTERNAL_REDIS_PID_FILE`.
    * **`redis.conf` Errors:** Check for syntax errors or invalid parameter values in `~/.config/grazr/redis/redis.conf`.
    * **Memory Overcommit:** Redis often warns about `vm.overcommit_memory`. For development, this is usually just a warning and doesn't prevent startup. For production, it should be addressed.
* **Connection Issues:**
    * Verify `redis-server` is running and on the correct port.
    * Ensure `bind` directive in `redis.conf` is set to `127.0.0.1 ::1` (or appropriate interface).
    * Check if a password is set (`requirepass` in `redis.conf`) if clients are failing to authenticate.

## 7. Contributing to Redis Management

* Improving the default `redis.conf` template provided by `_ensure_redis_config()` with more sensible defaults or options for local development.
* Adding UI features to configure more Redis settings (e.g., persistence, password).
* Enhancing the `bundle_redis.sh` script (e.g., to allow choosing different Redis versions to compile).