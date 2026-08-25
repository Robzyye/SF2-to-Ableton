# Third-party licenses

## soundfont-importer

This project's SoundFont (.sf2) parsing logic and Ableton `.adv` preset XML
structure were adapted from:

- Project: [soundfont-importer](https://github.com/norakorra/soundfont-importer)
- Author: Nora Korra (Aaron Werinussa)
- License: MIT

The original project targets Ableton Live's (beta) Extensions SDK to provide
an in-app "Import SoundFont" context-menu action. The code in this repository
reimplements the same underlying SF2-parsing and `.adv`-generation logic in
pure Python, as a standalone script that doesn't require the Extensions SDK
or Ableton Live 12 beta.

Its original MIT license text, reproduced here as required by its terms:

```
MIT License

Copyright (c) 2026 Aaron Werinussa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
