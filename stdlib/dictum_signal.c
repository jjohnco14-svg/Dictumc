#include "dictum_signal.h"
#include <signal.h>
#include <unistd.h>
#include <string.h>

static void (*user_handlers[64])(dictum_whole_t) = {0};

static void signal_wrapper(int sig) {
    if (sig >= 0 && sig < 64 && user_handlers[sig]) {
        user_handlers[sig]((dictum_whole_t)sig);
    }
}

void dictum_signal_on(dictum_whole_t sig, void (*handler)(dictum_whole_t)) {
    if (sig < 1 || sig >= 64) return;
    user_handlers[sig] = handler;
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = signal_wrapper;
    sigaction((int)sig, &sa, NULL);
}

dictum_truth_t dictum_signal_send(dictum_whole_t pid, dictum_whole_t sig) {
    return kill((pid_t)pid, (int)sig) == 0;
}

dictum_truth_t dictum_signal_block(dictum_whole_t sig) {
    if (sig < 1 || sig >= 64) return 0;
    sigset_t set;
    sigemptyset(&set);
    sigaddset(&set, (int)sig);
    return sigprocmask(SIG_BLOCK, &set, NULL) == 0;
}

dictum_truth_t dictum_signal_unblock(dictum_whole_t sig) {
    if (sig < 1 || sig >= 64) return 0;
    sigset_t set;
    sigemptyset(&set);
    sigaddset(&set, (int)sig);
    return sigprocmask(SIG_UNBLOCK, &set, NULL) == 0;
}
