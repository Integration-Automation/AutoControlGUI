"""Disposable process-tree proof that an inherited writer cannot outlive its original peer."""
import subprocess
import sys
import unittest

from .presence_linux_test_support import native_support


CONTROLLER = r'''
from dataclasses import asdict
import ctypes,json,os,select,socket,subprocess,sys,tempfile
from je_auto_control.utils.agent_runtime.presence_channel_linux import LinuxListener
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
if ctypes.CDLL(None).prctl(36,1,0,0,0)!=0:
    raise RuntimeError('disposable controller cannot own orphan retirement')
writer="""
import os,select,socket,sys
s=socket.socket(fileno=int(sys.argv[1]))
gate=int(sys.argv[2])
try:
    if not select.select([gate],[],[],3)[0]:
        raise RuntimeError('owned writer gate timed out')
    if os.read(gate,1)==b'G':
        s.send(b'{}')
finally:
    os.close(gate)
    s.close()
"""
connector="""
import json,os,subprocess,sys
from je_auto_control.utils.agent_runtime.presence_channel_linux import LinuxChannel
from je_auto_control.utils.agent_runtime.presence_endpoint_linux import LinuxEndpoint,FileIdentity
from je_auto_control.utils.agent_runtime.presence_peer_linux import LinuxPeerIdentity
v=json.loads(sys.argv[1])
v['directory_identity']=FileIdentity(**v['directory_identity'])
v['socket_identity']=FileIdentity(**v['socket_identity'])
v['listener_process']=LinuxPeerIdentity(**v['listener_process'])
with LinuxChannel.connect(LinuxEndpoint(**v),timeout=1) as ch:
    s=ch._owner._state.resources.connection
    gate=int(sys.argv[2])
    child=subprocess.Popen([sys.executable,'-c',sys.argv[3],str(s.fileno()),str(gate)],
        pass_fds=(s.fileno(),gate),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    os.close(gate)
    print(child.pid,flush=True)
    sys.stdin.buffer.read(1)
    os._exit(0)
"""
with tempfile.TemporaryDirectory(prefix='ac-orphan-channel-') as runtime:
    with LinuxListener.create(runtime) as listener:
        reader,writer_gate=os.pipe()
        child=subprocess.Popen([sys.executable,'-c',connector,json.dumps(asdict(listener.endpoint)),
            str(reader),writer],pass_fds=(reader,),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,bufsize=0)
        os.close(reader)
        descendant=None
        channel=None
        try:
            channel=listener.accept(timeout=1)
            if not select.select([child.stdout],[],[],3)[0]:
                raise RuntimeError('owned descendant PID was not reported')
            descendant=int(child.stdout.readline())
            output,errors=child.communicate(b'Q',timeout=3)
            if child.returncode or errors:
                raise RuntimeError((child.returncode,errors))
            os.write(writer_gate,b'G')
            try:
                channel.receive(timeout=1)
            except AgentTaskError:
                pass
            else:
                raise AssertionError('inherited writer revived exited original peer')
        finally:
            os.close(writer_gate)
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=3)
            if channel is not None:
                channel.close()
            if descendant is not None:
                actual,status=os.waitpid(descendant,0)
                if actual!=descendant or status!=0:
                    raise AssertionError(('owned descendant failed',actual,status))
print('original-exit-refused; connector-and-descendant-reaped')
'''


@unittest.skipUnless(sys.platform == 'linux', 'native Linux process tree proof required')
class ProcessWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native_support()

    def test_descendant_writer_after_original_exit_is_refused_and_reaped(self):
        result = subprocess.run([sys.executable, '-W', 'error', '-c', CONTROLLER], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stderr, b'')
        self.assertEqual(result.stdout.strip(), b'original-exit-refused; connector-and-descendant-reaped')
