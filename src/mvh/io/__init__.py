"""I/O helpers: atomic writes, float WAV (stdlib + numpy), the ffmpeg resolver and ffmpeg-only audio
decode/encode.

``atomic`` and ``wav`` import only the stdlib and numpy (the sep worker uses them). ``ffmpeg`` and ``audio``
are
stdlib + numpy too, but only the main env calls them.
"""
