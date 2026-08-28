import pyaudiowpatch as pyaudio

p = pyaudio.PyAudio()
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    host_api = p.get_host_api_info_by_index(info["hostApi"])
    print(i, info["name"], "|", host_api["name"], "| in:", info["maxInputChannels"], "out:", info["maxOutputChannels"])