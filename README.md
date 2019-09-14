# layo-haks
Resources that make up the NWN Layonara HAKs. Build instructions are provided below.

## Requirements for Building
* git https://git-scm.com/downloads
* nim https://github.com/dom96/choosenim
* layonara_nwn https://github.com/plenarius/layonara_nwn

## Installation

### Linux/Mac Users
* Install nim and git using your package manager of choice i.e. `apt install git nim`

### Windows Users
* If you don't already have git you need to install it from the above link or you may prefer a UI version like https://tortoisegit.org/
* Download and install choosenim here: https://github.com/dom96/choosenim/releases

### All Users
* Install layonara_nwn with `nimble install https://github.com/plenarius/layonara_nwn`

## Building Haks
You need to clone this repository either from a command line with the following command or using a UI interface for git that you downloaded:

`git clone https://github.com/plenarius/layo-haks`

Once that's complete you can build the haks by opening a prompt, `cd` into the newly cloned repository folder and running:

`layonara_nwn hak`

The haks will be output in the root of that folder for you to move where they belong.
