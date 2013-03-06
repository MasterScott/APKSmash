#!/usr/bin/python
#
#
# Version: 2.34		Last Update Date: 3/6/2013
#
# Contact: corey.benninger at intrepidusgroup.com 
#
# License: Public domain
#
#
# Intrepidus Group script to make reading Smali output easier by adding strings
# Run this in the same directory as the AndroidManifest.xml file after APKTool
#
# If massacring this APK with JonestownThisAPK = True, then make sure that
# "iglogger.smali" is copied into the "smali" directory before doing a build.
#
#
# Updates: Fixed bug that only found first issue in a class file
# ToDo: parse Manifest, look for non-standard files in zip (now in batch file)
#

import xml.dom.minidom
from xml.dom.minidom import Node
import re
import os
import tempfile

print "Starting fixstrings and apk analysis...\n"

##### This flag will insert debugging statements into the APK.
JonestownThisAPK = False

##### This the output file name. Look in here afterwards for the good stuff.
outputfilename = 'apk-ig-info.txt'

##### This defines searches below which need to log out a full SAMLI line of code
needs_extra_formatting = ['HTTP', 'HTTPS', 'DECRYPT']

##### These are the items to look for and how it should be listed in the 'outputfilename'
searchterms = {'android/content/Context;->openFileOutput': 'OpenFile',
	       'Landroid/os/Binder;->getCallingUid' : 'UID Check',
	       'Landroid/content/Context;->checkCallingOrSelfPermission': 'Calling PERMISSION check',
	       'Landroid/telephony/TelephonyManager;->getPhoneType': 'PhoneType check',
	       'Landroid/telephony/TelephonyManager;->getDevice': 'DEVICE NUM or ID check',
               'Landroid/os/Build;->BOARD': 'Emulator Check (BOARD)',
               'Landroid/os/Build;->DEVICE': 'Device Check',
               'android/util/Log;->': 'LOG',
               'Ljava/io/PrintStream;->println' : "LOG (println)",
               'method public static main': "TEST CODE 'main()' method",
               'Landroid/telephony/SmsManager': 'SMS Manager',
               'java/lang/System;->loadLibrary': 'LoadLibrary',
               'java/lang/Runtime;->exec': 'Runtime Exec',
               'Ljavax/net/ssl/TrustManager': 'SSL PINNING (trustmanager)',           
               'DEBUG:Z': 'DEBUG Boolean',
               '"su"': "Possible ROOT Detection 'su'",
               'superuser': "Possible ROOT Detection 'superuser'",
               'busybox': "Possible ROOT Detection 'busybox'",
               'debug': 'DEBUG',               
               'decrypt': 'DECRYPT',
               'https://': 'HTTPS',
               'http://': 'HTTP',
               'addJavascriptInterface': 'JAVASCRIPT Interface',
               'setJavaScriptEnabled': 'JAVASCRIPT Set Enabled ',
               'setPluginsEnabled': 'Webview Set PLUGINS Enabled Method',
               'Landroid/content/Intent;-><init>': 'INTENT being generated',
               'Landroid/content/Context;->getSharedPreferences': 'Shared Prefs used',
               'Landroid/database/sqlite/SQLiteDatabase;->openDatabase': 'SQLite Database Open cmd',
               'Landroid/os/Environment;->getExternalStorageDirectory': 'External Storage check',
               'Landroid/os/Environment;->DIRECTORY_PICTURES': 'Asking for Picture directory',
               'Ljava/net/HttpURLConnection': 'HttpURLConnection',
	       'Ljava/security': 'Java Lang Security',
               'Landroid/content/pm/PackageManager': 'PackageManager',
               'Landroid/net/ConnectivityManager': 'Possible Network Check - ConnectivityManger'
               }
               
regexsearchterms = {'"[\d]{9,10}"': 'PHONE NUMBER (9digits)',
                    '"[\d]{1,6}-[\d]{3}-[\d]{4}"': 'PHONE NUMBER (regex)',
                    '(?:\d{1,3}\.){3}\d{1,3}': 'IP Addresses',
                    'd{13,16}': 'LAME Check for CreditCard (...really)',
                    '((A-Za-z0-9+/){4,4})*(A-Z-a-z0-9+/=){4,4}': 'LAME Check Base64 (ends with two equals)',
                    '[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4}': 'EMAIL Address'
	           }
	           
	           

##### Opening Public and Strings XML files for fixing strings (change if English is not your thang)
doc_public_path = os.getcwd() + os.sep + "res" + os.sep + "values" + os.sep + "public.xml"
doc_strings_path = os.getcwd() + os.sep + "res" + os.sep + "values" + os.sep + "strings.xml"

if not os.path.isfile(doc_public_path): 
	print "Can not find public.xml file: " + doc_public_path
	exit();

if not os.path.isfile(doc_strings_path): 
	print "Can not find strings.xml file: " + doc_strings_path
	exit();
               
doc = xml.dom.minidom.parse(doc_public_path)
doc_strings = xml.dom.minidom.parse(doc_strings_path)
 
mymap = {}
mystrings = {}

##### Load our String values from the two files
for node in doc_strings.getElementsByTagName("string"):
	if node.hasChildNodes():
		name = node.getAttribute("name")
		data = node.firstChild.nodeValue
		#print data.encode("utf-8")
		if data is not None:
			mystrings[name] = data.replace('\n', '')
 
for node in doc.getElementsByTagName("public"):
	name = node.getAttribute("name")
	id = node.getAttribute("id")
	type = node.getAttribute("type")

	if type == 'string':
		if name in mystrings:
			mymap[id] = { 'name': name, 'type':type, 'stringval': mystrings[name].encode('ascii', 'replace')}			
		else:
			mymap[id] = { 'name': name, 'type':type, 'stringval': 'unknown'}
	else:
		mymap[id] = { 'name': name, 'type':type}



"""	
 Function (dir_byfiletype) lets us get all files based on extension from
 a directory and its subdirectories
"""

def dir_byfiletype(dir_name, *args):
	fileList = []
	for file in os.listdir(dir_name):
		dirfile = os.path.join(dir_name, file)
		if os.path.isfile(dirfile):
			if os.path.splitext(dirfile)[1][1:] in args:
				fileList.append(dirfile)
			pass
		if os.path.isdir(dirfile):
			fileList += dir_byfiletype(dirfile, *args)
  	return fileList



"""	
 Function (get_var_from_line) returns which string of the smali variable at a certain 
 position in the line. This can be useful if we later want to log out that variable.
 Note, if a method uses over 16 registers, it will typically need to swap things and
 use a virtual range. This causes me headaches and will probably screw things up.
"""
def get_var_from_line(line, varnumber):
	### If the line is a range, we need to count differently.
	if line.find("invoke-virtual/range") > 0:
		myregexstring = 'range \{(p|v)(\d+) '
		regex = re.compile(myregexstring)
		method_vars = regex.search(line).groups()
		return str(method_vars[0]) + str(int(method_vars[1]) + (varnumber -1))
		
	### Cheating here. there maybe more vars  but this should work since the list starts with " {"
	myregexstring = ' \{'
	for i in range(varnumber):
		myregexstring += '(p\d+|v\d+), '
	myregexstring = myregexstring[:-2] 
	
	regex = re.compile(myregexstring)
	method_vars = regex.search(line).groups()
	if len(method_vars) == varnumber:
		return str(method_vars[varnumber -1])
	else:
		print "ERROR: Couldn't find the right number of vars for this method"
			
	
	
	
"""	
 Function (find_openfile_perms) spits out what perm the file should be. 
 Not prefect, if there's a code branch just before this method
 it could end up with an unknown or incorrect value
"""

def find_openfile_perms(line, lastline):
	if line.find('android/content/Context;->openFileOutput'):
		file_var_perm = lastline[-1]
		file_var_name = ""
		
		# try to get the registers passed to the openFile, should always be 3 of them
		regex = re.compile(r'\{(p\d+|v\d+), (p\d+|v\d+), (p\d+|v\d+)}')
		file_vars = regex.search(line).groups()

		if len(file_vars) == 3:
			#The last one will be the permission setting
			#Ghetto search for last assignment to that register
			for oldlines in lastline:
				if oldlines.find(file_vars[2]) > 0:
					file_var_perm = str(oldlines.split(", ")[-1]).strip()
				if oldlines.find(file_vars[1]) > 0:
					file_var_name = str(oldlines.split(", ")[-1]).strip()
					
		return "Permssions Are: " + perm_to_string(file_var_perm)




"""	
 Function (perm_to_string) takes a line of smali and returns the const value
 in readable form as it relates to the file open command permissions. You should
 make sure you're sending the right line to this function.
"""

def perm_to_string(line):
	perm = "UNKNOWN"
	
	# We may get the full last line, which is for sure going to be the right
	# assignment, but typically is. So, split and get the value if it looks like a const
	if line.find('const'):
		linevalues = line.split(', ')
		if len(linevalues) == 2:
			line = linevalues[1]
			
	# Now we should just have the value
	# Most apps appear to use Hex, but I think this could other string values 
	# if it was doing something strange
	line = line.strip()
	if line == '0x0':
		perm = "NONE/DEFAULT_MASK"
	elif line == "0x1":
		perm = "WORLD_READ"
	elif line == "0x2":
		perm = "WORLD_WRITE"
	elif line == "0x3":
		perm = "WORLD_READWRITE"
	else:
		perm = "UKNOWN: " + line
	return perm


	
#####  XML read and loaded, now go thru code 

fileList = dir_byfiletype('smali', 'smali', 'java')
regex = re.compile(r'\b0x7f0\w{5}\b')
lines_this_method = []

##### New Method, clear stored values Counter is as follows: {searchterm: [count, [list_of_occurnces]]}
counter = {}
lastsearch = ""

for f in fileList:
        #print "Searching file: " + f
        
	smali_name = f
	smaliIn = open(smali_name, "r")

	tmp_fd, tmp_name = tempfile.mkstemp(suffix='.smalitemp')
	smaliOut = open(tmp_name, 'w+b')

	for line in smaliIn:

		##### New Method, clear stored values
		if line.find('.end method') == 0:
			lines_this_method = []
			
		hashcodes = regex.findall(line)
		for hashcode in hashcodes:
			lastline = lines_this_method[-1]
			if lastline[0:6] == "#FixS#":
				#print "Skipping, already updated.."
				continue
			
			if hashcode in mymap:
				if mymap[hashcode]['type'] == 'string':
					smaliOut.write("#FixS#" + mymap[hashcode]['type'] + ":" + mymap[hashcode]['name'] + "  VALUE:" + mymap[hashcode]['stringval'] + " \n")
				else:
					smaliOut.write("#FixS#" + mymap[hashcode]['type'] + ":" + mymap[hashcode]['name'] + " \n")
			else:
				smaliOut.write("#FixS# HASHCODE NOT FOUND: " + hashcode + "\n")

                ##### This will search for keys defined in the searchterms in the smali file
                ##### and then updates the counter data structure with the count of occurences
                ##### and there locations.
		for key, value in searchterms.iteritems():
                        if line.find(key) > 0:
                                if lastsearch == smali_name and lastkey == key:
                                        break
                                
                                format_output = value + " use found in: " + smali_name
                                if value == 'OpenFile':
                                        format_output += ' : ' + find_openfile_perms(line, lines_this_method)
                                elif value in needs_extra_formatting:
                                        format_output += ' : ' + line.rstrip()

                                ##### Updates the counter data structure...
                                if not counter.has_key(value):
                                        counter[value] = [0, []]
                                counter[value][0] += 1
                                counter[value][1].append(format_output)
                                
                                lastsearch = smali_name
                                lastkey = key
                                
                ##### This will look for REGEX search terms
		for key, value in regexsearchterms.iteritems():
                        if re.search(key, line) > 0:
                        	format_output = value + " use found in: " + smali_name
                        	format_output += ' : ' + line.rstrip()
                        	
                                ##### Updates the counter data structure...
                                if not counter.has_key(value):
                                        counter[value] = [0, []]
                                counter[value][0] += 1
                                counter[value][1].append(format_output)                        
                        
                        
                ##### Intents migth be interesting to know when they are being thrown and for what
                ##### Eventually we should log more about these
		if JonestownThisAPK and line.find('Landroid/content/Intent;-><init>(Ljava/lang/String;)V') > 0:
			smalivar =  get_var_from_line(line, 2)
			smaliOut.write("    invoke-static {" + smalivar + "}, Liglogger;->trace_intent(Ljava/lang/String;)I" + "\n")

		##### String compares are interesting.
		##### Log these out (should be two strings in the smali vars
		if JonestownThisAPK and ( line.find('Ljava/lang/String;->equals(Ljava/lang/Object;)Z') > 0 or line.find('Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z') > 0):
			if line.find("invoke-virtual/range") > 0:
				print "skipping virtual range"
			else:	
				smalivar1 =  get_var_from_line(line, 1)
				smalivar2 =  get_var_from_line(line, 2)
				smaliOut.write("    invoke-static {" + smalivar1 + ", " + smalivar2 + "}, Liglogger;->trace_stringcompare(Ljava/lang/String;Ljava/lang/String;)I" + "\n")


			
		##### This writes out the current line
		lines_this_method.append(line)
		smaliOut.write(line) 
		
		##### At this point, writes are adding after the orginal line of smali code
	
		##### JonesTown
		#####    To help with obfuscated apps, log out each time we enter a new method
		#####
		if JonestownThisAPK and line.find('prologue') > 0:
			smaliOut.write("    invoke-static {}, Liglogger;->trace_method()I" + "\n")
	
	smaliIn.close()
	smaliOut.close()
	os.close(tmp_fd)
	os.remove(smali_name)
	os.rename(tmp_name, smali_name)



print "Done Search. Writing output: " + outputfilename
f = open(outputfilename, 'w')
for key, value in counter.iteritems():
        if value[0] != 0:

                f.write("\n\n#################################\n" +
                             key + " : "  + str(value[0]) +
                         "\n#################################\n\n")
                         
                ##### Print all the occurences...
                for item in value[1]:
                        f.write(item + '\n')

f.close()
