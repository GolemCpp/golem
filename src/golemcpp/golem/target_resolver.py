'''
Settling what a build is for, once a compiler has been chosen.

Golem names no architecture nobody asked for, so the identity comes from the
compiler that waf actually selected, or from a request, or from both. This is
where those two are reconciled, and the reconciliation has to happen here
rather than earlier. Because only the compiler that was chosen can answer.

The vocabulary lives in `target_platform`, which knows nothing of waf and runs
no subprocess. This module is the other half: it asks a real toolchain real
questions and turns the answers into one of four outcomes.

- The compiler and the request agree, or only one of them named a target.
- They disagree, but a flag reaches what was asked and a build proves it.
- They disagree and nothing bridges it, which is an error.
- Nothing named a target at all, which is an error, since naming one here
  would be a guess and it would end up in a build slug.
'''

import subprocess

from waflib import Logs

from golemcpp.golem import target_platform


def arch_request(options):
    '''
    The architecture that was asked for, or '' when none was.

    Distinct from what the build turns out to be: an absent request is not a
    request for the host, and only a request may emit selecting flags.
    '''
    return target_platform.normalize_arch(getattr(options, 'arch', None))


def refusal_phrase(refusal, target):
    '''
    Say what a compiler builds for instead, completing "the selected compiler".

    Each refusal is about one of the compiler's own answers, so the phrase
    names that answer and leaves the request to the sentence around it.
    '''
    if refusal is target_platform.Refusal.ARCH:
        return "builds for '{}'".format(target.arch)

    if refusal is target_platform.Refusal.FAMILY:
        return "builds for the '{}' family".format(target.family)

    return ("builds for the '{}' ABI, and objects built for one ABI do not "
            "link with the other".format(target.abi))


class TargetResolver:
    '''
    Asks the chosen compiler what it builds for, and settles it against --arch.

    Reads waf's configuration context directly, so `msvc` is the one fact it
    cannot work out for itself: which toolchain family this is decides both
    how the compiler is asked and whether a flag could reach a second target.
    '''

    def __init__(self, conf, msvc=False):
        self.conf = conf
        self.msvc = msvc

    def compiler_triple(self):
        '''
        The target triple the compiler waf selected reports, or '' for none.

        `-dumpmachine` is the portable form; `-print-multiarch` is empty
        outside Debian. MSVC answers neither and is asked through DEST_CPU.
        '''
        if self.msvc:
            return ''

        cxx = self.conf.env.CXX
        if not cxx:
            return ''

        command = (list(cxx) if isinstance(cxx, list) else [cxx]) + [
            '-dumpmachine']
        try:
            return subprocess.check_output(
                command, universal_newlines=True,
                stderr=subprocess.DEVNULL).strip()
        except (OSError, ValueError, subprocess.SubprocessError):
            return ''

    def compiler_target(self):
        '''
        Everything the compiler waf selected said about what it builds for.

        MSVC is asked differently: waf's msvc detection records the target of
        the installation it found in DEST_CPU.
        '''
        if self.msvc:
            return target_platform.CompilerTarget.from_arch(
                self.conf.env.DEST_CPU)

        return target_platform.CompilerTarget.from_triple(
            self.compiler_triple())

    def compiler_builds_with(self, flags):
        '''
        Build a trivial program with `flags` and report whether that worked.

        The one question a compiler answers about a target it was not
        configured for. Multilib is why: the flag reaches a second target only
        where the platform ships a userland for it, and nothing short of
        linking says whether it does.
        '''
        return bool(self.conf.check_cxx(
            cxxflags=flags, linkflags=flags, mandatory=False,
            msg='Checking whether the compiler builds with {}'.format(
                ' '.join(flags))))

    def compiler_command(self):
        '''The compiler as it was invoked, for a message that has to name it.'''
        cxx = self.conf.env.CXX
        return ' '.join(cxx) if isinstance(cxx, list) else cxx

    def resolve(self):
        '''
        Name the architecture this build is for, or raise saying why it cannot.

        Called once, after waf's compiler detection and before the options are
        saved, because everything downstream reads them back rather than
        asking again.

        A request --arch= that the chosen compiler will not honour is an
        error. One that nothing could check is taken on trust, with a warning.
        '''
        requested = arch_request(self.conf.options)
        target = self.compiler_target()
        resolved, refusal = target.settle(requested)

        silent = not target.answered

        # A triple names the target a compiler was *configured* for, not the
        # only one it can reach: a multilib gcc says x86_64-linux-gnu and
        # builds i686 given -m32. It reports that nowhere -- `gcc -m32
        # -dumpmachine` still answers x86_64 -- so when Golem has flags for
        # the request, only an attempt to build with them can give an honest
        # answer. Only the x86 family carries any.
        #
        # A family or an ABI the compiler ruled out is settled and stays that
        # way. Those name a different target, not one alongside the one it
        # builds, and objects built for one ABI do not link with the other
        # however well a trivial program compiles.
        unsettled = (refusal is target_platform.Refusal.ARCH
                     or (requested and silent))

        attempted = []
        verified = False
        # MSVC takes no such flag, and its request already reached waf through
        # MSVC_TARGETS before detection ran.
        if unsettled and not self.msvc:
            attempted = list(
                target_platform.arch_capability(requested).gnu_flags)
            if attempted:
                verified = self.compiler_builds_with(attempted)
                if verified:
                    resolved, refusal = requested, None

        build_failed = bool(attempted) and not verified
        unverifiable = silent and not attempted

        if refusal:
            attempt = ''
            if build_failed:
                attempt = (" Building with {} was tried as well and produced "
                           "nothing that links, so it has no multilib for that "
                           "target either.".format(' '.join(attempted)))
            raise RuntimeError(
                "Requested architecture '{}' but the selected compiler ({}) "
                "{}.{}".format(requested, self.compiler_command(),
                               refusal_phrase(refusal, target), attempt))

        if not resolved:
            raise RuntimeError(
                "Cannot tell what architecture this build is for: the compiler "
                "did not say, and none was asked for with --arch. Naming one "
                "here would be a guess, and it would end up in the build slug "
                "and in what the artifact advertises about itself.")

        if silent and build_failed:
            raise RuntimeError(
                "Requested architecture '{}' but the selected compiler ({}) "
                "did not build for it: {} produced nothing that links, and it "
                "reported no target of its own to fall back on.".format(
                    requested, self.compiler_command(), ' '.join(attempted)))

        if unverifiable:
            # The request names the artifact on the user's word alone, so a
            # wrong one is cached under a wrong name.
            #
            # Rare, and not MSVC, which answers through DEST_CPU. Two sources:
            # NO_MSVC_DETECT, waf's escape hatch for an already-configured
            # Developer Command Prompt, which returns before writing DEST_CPU;
            # and a toolchain with no -dumpmachine, which is what waf's
            # compiler_cxx selects on SunOS and AIX. Both leave an environment
            # that is probably already correct and a user who was explicit, so
            # this warns rather than refusing.
            Logs.warn(
                "Building for '{}' on request alone: the selected compiler "
                "reported no target of its own, so nothing confirms it builds "
                "for that architecture.".format(resolved))

        # Log the resolved target architecture
        self.conf.msg('Target architecture', resolved)

        return resolved
