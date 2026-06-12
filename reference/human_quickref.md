# Human conversion quick-reference

Cheat for hand-translating events in run_human.
Open in a 2nd tab, or type `?` in run_human for all
of this, `?term` to filter (`?choice` `?111` `?item`).

## Controls  (work any time while typing)

EOF       submit the script
:undo     drop the last line you typed
:clear    wipe and start the script over
? / ?term refs (this sheet) / filtered
opus      punt the whole event to Opus
q         quit the session (progress saved)

## Codes  (RPG Maker -> Poryscript)

101 show text      -> msgbox("...")
401 text continued -> append to prev msgbox
102 show choices   -> multichoice + switch
402 when [choice]  -> case N:
403 when cancel    -> handle cancel
404 end choices    -> close the switch
111 if branch      -> if (...) {
411 else           -> } else {
412 branch end     -> }
123 set selfswitch -> setflag(<SSx>)
117 call common ev -> call CommonEvent_NNN
106 wait           -> drop it
108 comment        -> drop it
201 transfer/warp  -> off-lane: opus

## Skeleton  (every interactive event)

lock          # freeze during the scene
faceplayer    # talk-to NPCs only (not signs)
msgbox("...")
release
end

Self-switch event: add setflag(<SSx>) too.
An empty page (no commands) -> just  end

## Dialogue text

\n  keep: newline in the box
\p  keep: new page / scroll
{PLAYER} {RIVAL}  keep: name slots
Trim outer spaces. Preserve meaning.

### STRIP these (no GBA equivalent)

\c[n]     color
\wt[n]    wait n frames
\wtnp[n]  wait, no pause
\sign[..] sign frame
\b  \r    style toggles

## Flags & vars

setflag(FLAG_X)    clearflag(FLAG_X)
if (flag(FLAG_X))
setvar(VAR_X, 3)   addvar(VAR_X, 1)
if (var(VAR_X) == 3)
copyvar(VAR_DST, VAR_SRC)
random(3) -> 0..2 into VAR_RESULT
Use only names the UI shows / already exist.
A NEW global flag/var -> punt with  opus

## Items / party

giveitem(ITEM_POTION, 1)   # fanfare auto
checkitem(ITEM_X)          # -> VAR_RESULT
healparty
ground item pbItemBall(X) -> giveitem(X, 1)

## Yes / No

msgbox("...?", MSGBOX_YESNO)
if (var(VAR_RESULT) == 1) {   # 1=Yes 0=No
    ...
} else {
    ...
}

## Stuck on ONE command

# UNHANDLED: what it does
(leave the breadcrumb, translate the rest)

## Stuck on the WHOLE event

type  opus  to punt it to the bulk run.
