RFCat SubGHz Protocol Support

I would like to add radio frequency protocol support to rfcat. To understand rfcat, read the documentation in @docs/rfcat.
Protocol implementations already exist in Flipper's firmware and are available on disk at /home/dev/src/flipperzero-firmware/lib/subghz/. Documentation for this implementation, and guidance on how to implement these protocols in python exist at /home/dev/src/rfcat/docs/flipper-subghz.md.

Start by implementing static RF protocols (that work using fixed code) like Princeton and GateTX. Ensure that the implementation provides easy hooks to receive/decode and send/encode data with rfcat.

Place the new Python code in /home/dev/src/rfcat/rflib/protocols. Do not modify existing rfcat code. We want this change to be purely additive. Use LSP to explore code. `clangd` is available at /home/dev/.local/bin/clangd. /home/dev/src/rfcat has its own virtual environment. Activate it using `source /home/dev/src/rfcat/.venv/bin/activate` before exploring Python code in rfcat.
Ask questiond. Do not make assumptions.
