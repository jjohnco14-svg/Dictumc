#ifndef DICTUM_SIGNAL_H
#define DICTUM_SIGNAL_H

#include "dictum_core.h"

/* Dictum interface:
module Signal:
    action on takes Sig as whole number and Handler as action produces nothing
    action send takes Pid as whole number and Sig as whole number produces truth value
    action block takes Sig as whole number produces truth value
    action unblock takes Sig as whole number produces truth value
end module
*/

void dictum_signal_on(dictum_whole_t sig, void (*handler)(dictum_whole_t));
dictum_truth_t dictum_signal_send(dictum_whole_t pid, dictum_whole_t sig);
dictum_truth_t dictum_signal_block(dictum_whole_t sig);
dictum_truth_t dictum_signal_unblock(dictum_whole_t sig);

#endif
