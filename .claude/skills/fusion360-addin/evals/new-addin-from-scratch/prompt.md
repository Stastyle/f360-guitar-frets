---
tags: [fusion360-addin]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

I want a new Fusion 360 add-in for making parametric finger-joint (box joint) boxes for my laser-cut plywood projects. Inputs: outer length/width/height, material thickness, finger width, and a checkbox for an open top. It should create the six panels as bodies in a new component so I can lay them flat later. Set the project up in ./FingerBox with everything I need to install it in Fusion, and make the joint math testable here since I only have Fusion on my Windows laptop at home. I don't need the full geometry perfect yet, but the project structure, the dialog and the math with tests should be solid.
