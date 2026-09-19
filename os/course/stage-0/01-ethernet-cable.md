---
stage: 0
title: Make an Ethernet cable
skills: [Network infrastructure]
---

# Make an Ethernet cable

Every network you will ever touch starts with a cable somebody crimped. Today
that somebody is you.

## Why this matters
A bad crimp is the single most common fault in a small network, and it looks
exactly like a broken router. Learning to make and *test* a cable means you can
rule it out in thirty seconds for the rest of your life.

## Steps

1. **Cut and strip.** Take about 60cm of cable. Strip 25mm of the outer jacket.
   Do not nick the inner wires — if you do, cut it back and start again.
2. **Sort to T568B.** Left to right, clip facing away from you:
   orange-white, orange, green-white, blue, blue-white, green, brown-white, brown.
3. **Trim flat.** Hold the order, trim the ends square, about 12mm past the jacket.
4. **Seat in the plug.** Every wire must reach the far end of the connector, and
   the jacket must sit inside the strain relief.
5. **Crimp.** Firm and complete. You will hear it.
6. **Repeat** so you have two cables: wall to router, and router to your server.

## Test it
Use the cable tester. All eight pins must light in order, 1 through 8.

> A cable that passes on pins 1,2,3,6 but fails 4,5,7,8 will still carry
> internet at 100Mb. It is still wrong. Fix it now, not in Stage 3 when you are
> chasing a "slow server".

## Evidence
- A photo of your finished plug, looking through the clear end so the colour
  order is visible.
- A photo of the tester with all eight lights lit.
