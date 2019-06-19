import subprocess
import sys

HAK_DIRS = [ "config","creatures","doors","gff","icons","item_models","palettes","placeables","portraits","unsorted","vfx" ]
BIG_DIRS = ["parts", "tilesets"]

def build_haks():
    for t in HAK_DIRS:
        print("Processing %s hak directory" % t)
        subprocess.call("nwn_erf -e HAK -c %s/* -f %s.hak && /bin/mv %s.hak /layonara/ee/userdir/hak/" % (t, t, t), shell=True, executable='/bin/bash')
    print("Processing parts1 hak directory")
    subprocess.call("nwn_erf -e HAK -c parts/male/{b*,d*,e*,g*,p*,s*,w*} -f parts1.hak && /bin/mv parts1.hak /layonara/ee/userdir/hak/", shell=True, executable='/bin/bash')
    print("Processing parts2 hak directory")
    subprocess.call("nwn_erf -e HAK -c parts/male/h* -f parts2.hak && /bin/mv parts2.hak /layonara/ee/userdir/hak/", shell=True, executable='/bin/bash')
    print("Processing parts3 hak directory")
    subprocess.call("nwn_erf -e HAK -c parts/female/{b*,d*,e*,g*,s*,w*} -f parts3.hak && /bin/mv parts3.hak /layonara/ee/userdir/hak/", shell=True, executable='/bin/bash')
    print("Processing parts4 hak directory")
    subprocess.call("nwn_erf -e HAK -c parts/female/h* -f parts4.hak && /bin/mv parts4.hak /layonara/ee/userdir/hak/", shell=True, executable='/bin/bash')
    print("Processing tiles1 hak directory")
    subprocess.call("nwn_erf -e HAK -c tilesets/{eld*,p*,tb*,tc*} -f tiles1.hak && /bin/mv tiles1.hak /layonara/ee/userdir/hak/", shell=True, executable='/bin/bash')
    print("Processing tiles2 hak directory")
    subprocess.call("nwn_erf -e HAK -c tilesets/t[d-p]* -f tiles2.hak && /bin/mv tiles2.hak /layonara/ee/userdir/hak/", shell=True, executable='/bin/bash')
    print("Processing tiles3 hak directory")
    subprocess.call("nwn_erf -e HAK -c tilesets/t[q-z]* -f tiles3.hak && /bin/mv tiles3.hak /layonara/ee/userdir/hak/", shell=True, executable='/bin/bash')
    print("Processing tiles4 hak directory")
    subprocess.call("nwn_erf -e HAK -c tilesets/[u-z]* -f tiles4.hak && /bin/mv tiles4.hak /layonara/ee/userdir/hak/", shell=True, executable='/bin/bash')
    print("Processing tiles5 hak directory")
    subprocess.call("nwn_erf -e HAK -c tilesets/{mini*,load*,shar*} -f tiles5.hak && /bin/mv tiles5.hak /layonara/ee/userdir/hak/", shell=True, executable='/bin/bash')

def main():
    build_haks()

if __name__ == '__main__':
    sys.exit( main() )