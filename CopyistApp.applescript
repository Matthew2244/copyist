-- Copyist.app — the same Copyist that runs at the terminal, wrapped in
-- dialogs a screen reader reads. Rebuild after editing:
--
--   osacompile -o /Applications/Copyist.app ~/copyist/CopyistApp.applescript
--
-- House rules (learned on YouTube Download.app, measured, not guessed):
-- every `do shell script` exports a real PATH first (a GUI app gets a
-- bare one); an information dialog has ONE button set as cancel only,
-- so Escape and Space both work; every list carries a Back item,
-- because `choose from list` ignores Escape; Escape's error -128 is
-- caught everywhere; long work sits inside `with timeout`.

on sh(cmd)
	do shell script "export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:\"$HOME/bin\"; " & cmd
end sh

on info(msg)
	try
		display dialog msg buttons {"OK"} cancel button "OK" with title "Copyist"
	end try
end info

on baseName(p)
	set tid to AppleScript's text item delimiters
	set AppleScript's text item delimiters to "/"
	set b to last text item of p
	set AppleScript's text item delimiters to tid
	return b
end baseName

on readLast()
	try
		return sh("cat \"$HOME/.config/copyist/app-last-chart\" 2>/dev/null")
	on error
		return ""
	end try
end readLast

on saveLast(p)
	try
		sh("mkdir -p \"$HOME/.config/copyist\"; printf %s " & quoted form of p & " > \"$HOME/.config/copyist/app-last-chart\"")
	end try
end saveLast

on pickChart()
	set lastPath to readLast()
	if lastPath is not "" then
		set sameItem to "Same chart: " & baseName(lastPath)
		set choice to choose from list {sameItem, "Pick a different chart", "Back"} with prompt "Which chart are we working on? Back returns to the menu." default items {sameItem} with title "Copyist"
		if choice is false then return ""
		set c to item 1 of choice
		if c is "Back" then return ""
		if c is sameItem then return lastPath
	end if
	try
		set defLoc to alias ((path to home folder as text) & "Library:Mobile Documents:com~apple~CloudDocs:Copyist Charts:")
	on error
		set defLoc to path to home folder
	end try
	try
		set f to choose file with prompt "Pick a .chart file." default location defLoc
	on error
		return ""
	end try
	set p to POSIX path of f
	saveLast(p)
	return p
end pickChart

on runChart(p, mode, doing)
	info(doing & " Press OK and hold tight — the big charts take a minute, and a dialog will bring the news.")
	with timeout of 1800 seconds
		set out to sh("chart " & quoted form of p & " " & mode & " 2>&1 | tail -n 6")
	end timeout
	info(out)
end runChart

on readPart(p)
	set d to sh("dirname " & quoted form of p)
	try
		set found to sh("cd " & quoted form of d & " && { ls | grep ' read aloud.txt$' || true; }")
	on error errText
		info("Could not look inside the chart's folder — " & errText)
		return
	end try
	if found is "" then
		info("No read-alouds here yet — build or check the chart first; they land beside it.")
		return
	end if
	set names to paragraphs of found
	set choice to choose from list (names & {"Back"}) with prompt "Which part should TextEdit open? VoiceOver reads it like a letter." with title "Copyist"
	if choice is false then return
	set c to item 1 of choice
	if c is "Back" then return
	sh("open -e " & quoted form of (d & "/" & c))
end readPart

on currentValue(key)
	set v to sh("chart settings | sed -n 's/.*" & key & " (now: \\(.*\\)) — .*/\\1/p'")
	if v is "not set" then return ""
	return v
end currentValue

on settingsDesk()
	repeat
		set desk to sh("chart settings")
		set choice to choose from list {"composer", "look", "notify", "open", "Back"} with prompt desk & return & "Change which one?" with title "Copyist"
		if choice is false then exit repeat
		set k to item 1 of choice
		if k is "Back" then exit repeat
		try
			if k is "notify" or k is "open" then
				set onoff to choose from list {"yes", "no", "Back"} with prompt "Set " & k & " to:" with title "Copyist"
				if onoff is false then
					set v to "Back"
				else
					set v to item 1 of onoff
				end if
			else
				set hint to ""
				if k is "look" then set hint to " The looks are jazz, handwritten, engraved and plain; empty lets each chart decide."
				set d to display dialog "New value for " & k & "." & hint buttons {"Cancel", "Set"} default button "Set" cancel button "Cancel" default answer currentValue(k) with title "Copyist"
				set v to text returned of d
			end if
			if v is not "Back" then
				info(sh("chart set " & quoted form of (k & "=" & v)))
			end if
		on error number -128
		end try
	end repeat
end settingsDesk

on run
	repeat
		set choice to choose from list {"Build — pages, listen MP3, findings", "Check — compile only, nothing rendered", "Read a part aloud", "Settings — the defaults desk", "Help — what this is", "Quit"} with prompt "Copyist — from your played demo to pages a band can read. What are we doing?" with title "Copyist" default items {"Build — pages, listen MP3, findings"}
		if choice is false then exit repeat
		set c to item 1 of choice
		if c is "Quit" then exit repeat
		try
			if c starts with "Build" then
				set p to pickChart()
				if p is not "" then runChart(p, "", "Building the whole desk: pages, the listen MP3, read-alouds and findings.")
			else if c starts with "Check" then
				set p to pickChart()
				if p is not "" then runChart(p, "c", "Checking the chart — every measure gets counted.")
			else if c starts with "Read" then
				set p to pickChart()
				if p is not "" then readPart(p)
			else if c starts with "Settings" then
				settingsDesk()
			else if c starts with "Help" then
				info("Copyist turns a chart file — plain words and a played demo — into engraved parts, a conductor score, spoken read-alouds and a listening MP3, all its own ink. Write charts with any text editor; the guide is CHART-WRITING in the Copyist Charts folder. The same brain answers to 'chart' in the terminal.")
			end if
		on error number -128
		end try
	end repeat
end run
