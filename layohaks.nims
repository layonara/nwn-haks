import strformat

var dir_list = listDirs("./")
for dir in dir_list:
  if (dir != "./.git" and dir != "./tilesets" and dir != "./parts"):
    echo fmt"Building {dir}.hak"
    exec(fmt"nwn_erf -e HAK -c {dir} -f {dir}.hak")
exec("nwn_erf -e HAK -c parts/male/{b*,d*,e*,g*,p*,s*,w*} -f parts1.hak")
exec("nwn_erf -e HAK -c parts/male/h* -f parts2.hak")
exec("nwn_erf -e HAK -c parts/female/{b*,d*,e*,g*,s*,w*} -f parts3.hak")
exec("nwn_erf -e HAK -c parts/female/h* -f parts4.hak")
exec("nwn_erf -e HAK -c tilesets/{eld*,p*,tb*,tc*} -f tiles1.hak")
exec("nwn_erf -e HAK -c tilesets/t[d-p]* -f tiles2.hak")
exec("nwn_erf -e HAK -c tilesets/t[q-z]* -f tiles3.hak")
exec("nwn_erf -e HAK -c tilesets/[u-z]* -f tiles4.hak")
exec("nwn_erf -e HAK -c tilesets/{mini*,load*,shar*} -f tiles5.hak")
