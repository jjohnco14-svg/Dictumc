#include "dictum_process.h"
#include "dictum_path.h"
#include <unistd.h>
#include <time.h>
#include <sys/wait.h>
#include <signal.h>
#include <errno.h>
#include <string.h>
#include <stdlib.h>

dictum_result_t dictum_process_spawn(const char* path, const char* args) {
    if (!dictum_path_valid(path)) {
        return DICTUM_FAILURE("Invalid executable path");
    }
    if (strpbrk(args, ";|&<>$`\"\'")) {
        return DICTUM_FAILURE("Invalid characters in arguments");
    }

    pid_t pid = fork();
    if (pid < 0) {
        return DICTUM_FAILURE(strerror(errno));
    }

    if (pid == 0) {
        /* Child process */
        char* args_copy = dictum_strdup(args);
        char* argv[64];
        int argc = 0;
        char* token = strtok(args_copy, " ");
        while (token && argc < 63) {
            argv[argc++] = token;
            token = strtok(NULL, " ");
        }
        argv[argc] = NULL;
        execvp(path, argv);
        _exit(127);
    }

    return DICTUM_SUCCESS((dictum_whole_t)pid);
}

dictum_whole_t dictum_process_wait(dictum_whole_t pid) {
    int status;
    int retries = 300;
    struct timespec ts = {0, 100000000};  /* 100ms */
    while (retries-- > 0) {
        pid_t result = waitpid((pid_t)pid, &status, WNOHANG);
        if (result == pid) {
            return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
        }
        if (result < 0) return -1;
        nanosleep(&ts, NULL);
    }
    kill((pid_t)pid, SIGTERM);
    return -1;
}

dictum_truth_t dictum_process_kill(dictum_whole_t pid) {
    return kill((pid_t)pid, SIGTERM) == 0;
}

dictum_whole_t dictum_process_current_id(void) {
    return (dictum_whole_t)getpid();
}
