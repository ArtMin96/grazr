# Grazr (Alpha)

![Grazr Logo](/assets/icons/logo.png) **A user-friendly, Herd-like local development environment for Linux (Ubuntu).**

Grazr simplifies managing your local development stack, including multiple PHP versions, Nginx, databases (MySQL, PostgreSQL), caching (Redis), object storage (MinIO), and Node.js versions (via NVM), all through an intuitive graphical interface.

---

**⚠️ This project is currently in Alpha. Expect bugs and rapid changes. ⚠️**

---

## Key Features

* **Bundled Services:** Manages its own isolated versions of Nginx, PHP (multiple versions), MySQL/MariaDB, PostgreSQL (multiple versions/instances), Redis, and MinIO.
* **PHP Version Management:** Easily switch PHP versions per site. Install and manage multiple PHP versions compiled from source.
* **PHP Extension & INI Management:** Enable/disable common PHP extensions and edit `php.ini` settings directly from the UI for each PHP version (CLI and FPM).
* **Site Management:** Link local project directories, and Grazr will automatically configure Nginx to serve them.
* **Custom Domains:** Uses `.test` TLD (configurable) for local sites, with automatic `/etc/hosts` file management.
* **Local SSL:** Automatic SSL certificate generation and management for your local sites using a bundled `mkcert` (installs its own local CA).
* **Node.js Version Management:** Integrates a bundled NVM to install and manage multiple Node.js versions, selectable per site.
* **User-Friendly GUI:** Built with PySide6 (Qt6) for a clean and modern interface.
* **Background Task Processing:** Keeps the UI responsive during longer operations.

## Screenshots

*(Consider adding a few key screenshots of the UI here. You've provided several, like `image_ca0d71.png` showing the Sites page)*

Example:
`![Grazr Sites Page](docs/screenshots/grazr_sites_page.png)` `![Grazr Services Page](docs/screenshots/grazr_services_page.png)`

## Tech Stack

* **Core Application:** Python 3.10+
* **User Interface:** PySide6 (Qt6)
* **Bundled Services (Examples):**
    * Nginx
    * PHP (multiple versions, compiled from source)
    * MySQL/MariaDB (bundled)
    * PostgreSQL (multiple versions, compiled from source)
    * Redis (compiled from source)
    * MinIO (binary)
    * NVM (script)
    * mkcert (binary)

## Installation

### For End-Users (Planned - .deb Package)

Once a `.deb` package is available:
```bash
sudo apt install ./grazr_VERSION_ARCH.deb
```
Grazr will then be available in your application menu. On first use of SSL features, Grazr will guide you through installing the `mkcert` local CA (which may require your sudo password).

### For Developers / Running from Source

Please refer to our comprehensive **[Contributor & Development Guide](docs/CONTRIBUTING.md)** for detailed instructions on prerequisites, setup, and running Grazr from source.

## Basic Usage

1.  Launch Grazr from your application menu or by running `python -m grazr.main` from the project root (in a development setup).
2.  **Services Tab:** Start/stop core services like Nginx, MySQL, PostgreSQL, Redis, MinIO. Add new database instances.
3.  **PHP Tab:** Manage bundled PHP versions, enable/disable extensions, and edit `php.ini` settings.
4.  **Sites Tab:**
    * Click "+ Add Site" to link a local project directory. Grazr will generate an Nginx configuration and a `.test` domain.
    * Select a site to manage its PHP version, Node.js version, and enable/disable SSL.
5.  **Node Tab:** Install and manage different Node.js versions using the bundled NVM.

## Documentation

We have detailed documentation for contributors and developers covering various aspects of Grazr:

* **[Main Contributor & Development Guide](docs/CONTRIBUTING.md)**
* **Service Management:**
    * [PHP Management](docs/services/PHP_Management.md)
    * [Nginx Management](docs/services/NGINX_MANAGEMENT.md)
    * [PostgreSQL Instance Management](docs/services/PostgreSQL_Instance_Management.md)
    * [MySQL / MariaDB Management](docs/services/MySQL_Management.md)
    * [Redis Management](docs/services/Redis_Management.md)
    * [MinIO Management](docs/services/MinIO_Management.md)
    * [Node.js (NVM) Management](docs/services/Node_Management.md)
    * [SSL (mkcert) Management](docs/services/SSL_Management_mkcert.md)
* **Core System:**
    * [Process Management (`process_manager.py`)](docs/core/Core_System_Process_Manager.md)
    * [Worker Thread & Task Handling (`worker.py`)](docs/core/Worker_And_Task_Handling.md)
    * [Configuration System & Shims (`config.py`, shims, `cli.py`)](docs/core/Core_System_Configuration_and_Shims.md)
* **User Interface:**
    * [UI Development Guide](docs/UI_Development_Guide.md)
    * [Registering Icons & Assets](docs/Registering_Icons.md)
* **Packaging:**
    * [Packaging Guide (.deb)](docs/Packaging_Guide.md)

## Contributing

We welcome contributions to Grazr! Whether it's bug reports, feature requests, documentation improvements, or code contributions, please feel free to get involved.

Please read our **[Contributor & Development Guide](docs/CONTRIBUTING.md)** for details on:
* Setting up your development environment.
* Coding style and standards.
* The development workflow and branching strategy.
* How to submit pull requests.
* Reporting bugs and suggesting features.

## License

This project is licensed under the [MIT License](LICENSE.md) (or your chosen license - create a LICENSE.md file).

## Acknowledgements

* Inspired by tools like Laravel Herd.
* Built with Python and the amazing PySide6 (Qt) framework.
* Utilizes fantastic open-source services like Nginx, PHP, MySQL, PostgreSQL, Redis, MinIO, NVM, and mkcert.