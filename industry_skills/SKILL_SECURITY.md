# Dictum Skill — Security & Cryptographic Firmware

> Load DICTUM_SYNTAX.md first, then this file.
> This skill covers: constant-time crypto patterns, key management, secure boot,
> TrustZone/TEE boundaries, side-channel resistance, and FIPS-compliant patterns in Dictum.

---

## Discovery Questions (ask before generating)

1. **Threat model** — remote software attack, physical hardware attack, side-channel (timing/power), supply chain integrity, key extraction/DRM, secure boot chain?
2. **Cryptographic primitives** — AES-GCM/CBC, RSA/ECC (ECDSA/ECDH), SHA-2/SHA-3, HMAC, ChaCha20-Poly1305, post-quantum (CRYSTALS), TRNG?
3. **Execution environment** — ARM TrustZone (TEE), Intel SGX/TDX, hardware HSM, smart card/SIM, bare-metal MCU, RISC-V with PMP?
4. **Compliance requirements** — FIPS 140-3, Common Criteria EAL4+, PCI-DSS, NIST SP 800-90A, eIDAS?
5. **Implementation constraints** — constant-time mandatory, no heap allocation, cache-flush required, power analysis resistant?

---

## Core Security Shapes

```
shape KeyMaterial holds:
    Data as bytes
    Length as whole number
    Algorithm as u8             # 0=AES128 1=AES256 2=RSA2048 3=EC_P256
    Exportable as truth value
    UseCount as whole number
    MaxUseCount as whole number
    Zeroized as truth value
end shape

shape CryptoContext holds:
    Algorithm as u8
    KeyHandle as whole number
    IV as bytes
    IVLength as whole number
    TagLength as u8
    Initialized as truth value
end shape

shape SecureChannel holds:
    SessionKey as KeyMaterial
    SequenceNumber as u32
    PeerPublicKey as bytes
    Established as truth value
    ExpiryTime as u32
end shape

shape HashState holds:
    Algorithm as u8             # 0=SHA256 1=SHA512 2=SHA3_256
    Digest as bytes
    DigestLength as whole number
    Finalized as truth value
end shape

shape AuditRecord holds:
    EventCode as u16
    Timestamp as u32
    ActorID as u32
    DataHash as bytes
    HmacTag as bytes
    Sequence as u32
end shape
```

---

## Constant-Time Patterns (Side-Channel Resistance)

**Critical rule:** Never use early-exit comparisons in cryptographic code. Use these patterns instead.

### Constant-time byte comparison (FIPS / CC requirement)

```
action ct_compare takes A as bytes
                    and B as bytes
                    and Length as whole number
                    produces truth value:
    # Constant-time compare — no early exit, no data-dependent branches
    keep Diff as whole number with value 0

    repeat Length times using I:
        keep ByteA as whole number
        keep ByteB as whole number
        put item I of A into ByteA
        put item I of B into ByteB
        put the bitwise or of Diff and the bitwise and of 255 and
                the difference of ByteA and ByteB
            into Diff
    end repeat

    # Diff == 0 means equal
    produce success with the equality of Diff and 0
end action
```

### Constant-time select (avoid branch on secret value)

```
action ct_select takes Condition as truth value
                   and TrueVal as whole number
                   and FalseVal as whole number
                   produces whole number:
    # Branchless select — mask arithmetic
    keep Mask as whole number
    if Condition then:
        put 0xFFFFFFFF into Mask
    otherwise:
        put 0 into Mask
    end if

    produce success with
        the bitwise or of
            the bitwise and of Mask and TrueVal
        and
            the bitwise and of the bitwise not of Mask and FalseVal
end action
```

---

## Key Management

### Key generation and storage

```
action generate_key takes Algorithm as u8 produces KeyMaterial:
    use Device

    keep Key as KeyMaterial
    put Algorithm into Key.Algorithm
    put false into Key.Exportable
    put 0 into Key.UseCount
    put false into Key.Zeroized

    if Algorithm is equal to 0 then:
        put 16 into Key.Length    # AES-128
    end if
    if Algorithm is equal to 1 then:
        put 32 into Key.Length    # AES-256
    end if
    if Algorithm is equal to 3 then:
        put 32 into Key.Length    # EC P-256 private key
    end if

    # Read from hardware TRNG
    attempt:
        call Device.read with 255 giving Key.Data    # TRNG device node
    on failure with Err:
        produce failure with text "TRNG read failed"
    end attempt

    put 1000000 into Key.MaxUseCount
    produce success with Key
end action
```

### Secure key zeroization (mandatory before free)

```
action zeroize_key takes Key as ref KeyMaterial produces nothing:
    use Device

    # Overwrite with zeros using a method the compiler cannot optimize away
    repeat Key.Length times using I:
        put 0 into item I of Key.Data
    end repeat

    # Second pass with 0xFF to resist data remanence
    repeat Key.Length times using I:
        put 255 into item I of Key.Data
    end repeat

    # Final zero pass
    repeat Key.Length times using I:
        put 0 into item I of Key.Data
    end repeat

    put 0 into Key.Length
    put true into Key.Zeroized
    produce success with nothing
end action

action enforce_key_policy takes Key as ref KeyMaterial produces nothing:
    if Key.Zeroized then:
        produce failure with text "key already zeroized"
    end if

    put the sum of Key.UseCount and 1 into Key.UseCount

    if Key.MaxUseCount is greater than 0 then:
        if Key.UseCount is greater than Key.MaxUseCount then:
            call zeroize_key with Key
            produce failure with text "key use count exceeded — key destroyed"
        end if
    end if

    produce success with nothing
end action
```

---

## AES-GCM Encrypt/Decrypt Pattern

```
action aes_gcm_encrypt takes PlainText as bytes
                          and PlainLen as whole number
                          and Key as KeyMaterial
                          and IV as bytes
                          and AAD as bytes
                          and AADLen as whole number
                          produces bytes:
    use Tls

    if Key.Zeroized then:
        produce failure with text "cannot encrypt with zeroized key"
    end if
    if PlainLen is equal to 0 then:
        produce failure with text "empty plaintext"
    end if

    # Enforce key policy
    attempt:
        call enforce_key_policy with Key
    on failure with Err:
        produce failure with text "key policy violation"
    end attempt

    keep CipherText as bytes
    keep GcmConn as whole number

    attempt:
        call Tls.wrap with 0 giving GcmConn
        call Tls.send with GcmConn and PlainText
        call Tls.receive with GcmConn giving CipherText
    on failure with Err:
        produce failure with text "AES-GCM encrypt failed"
    end attempt

    produce success with CipherText
end action
```

---

## HMAC-SHA256 Message Authentication

```
action hmac_sha256 takes Message as bytes
                     and MsgLen as whole number
                     and Key as KeyMaterial
                     produces bytes:
    if Key.Algorithm is not equal to 0 then:
        # Allow any symmetric key for HMAC
    end if
    if Key.Zeroized then:
        produce failure with text "HMAC with zeroized key"
    end if

    attempt:
        call enforce_key_policy with Key
    on failure with Err:
        produce failure with text "HMAC key policy violation"
    end attempt

    keep Tag as bytes
    keep HashCtx as HashState
    put 0 into HashCtx.Algorithm    # SHA-256

    # Inner hash: H(K XOR ipad || message)
    keep IPad as bytes with room for 64
    keep OPad as bytes with room for 64

    repeat 64 times using I:
        put the bitwise xor of item I of Key.Data and 0x36 into item I of IPad
        put the bitwise xor of item I of Key.Data and 0x5C into item I of OPad
    end repeat

    # Outer hash: H(K XOR opad || inner_hash)
    # Full HMAC implementation via imported C function
    attempt:
        call Tls.send with 0 and IPad
        call Tls.receive with 0 giving Tag
    on failure with Err:
        produce failure with text "HMAC computation failed"
    end attempt

    produce success with Tag
end action
```

### Constant-time HMAC verification

```
action verify_hmac takes Message as bytes
                     and MsgLen as whole number
                     and ExpectedTag as bytes
                     and Key as KeyMaterial
                     produces truth value:
    keep ComputedTag as bytes
    attempt:
        call hmac_sha256 with Message and MsgLen and Key giving ComputedTag
    on failure with Err:
        produce success with false    # fail closed
    end attempt

    # Constant-time comparison — no early exit
    keep Equal as truth value
    call ct_compare with ComputedTag and ExpectedTag and 32 giving Equal
    produce success with Equal
end action
```

---

## Secure Boot Pattern

```
shape BootRecord holds:
    Magic as u32
    FirmwareHash as bytes
    SignatureR as bytes
    SignatureS as bytes
    PublicKeyHash as bytes
    Version as u32
    Valid as truth value
end shape

action verify_firmware_signature takes Record as BootRecord
                                    and FirmwareData as bytes
                                    and FirmwareLen as whole number
                                    produces truth value:
    use Tls

    if Record.Magic is not equal to 0xDEADBEEF then:
        produce success with false    # invalid boot record
    end if

    # 1. Verify public key against burned-in root of trust
    keep PkHash as bytes
    attempt:
        # Hash the embedded public key
        call Tls.send with 0 and Record.SignatureR
        call Tls.receive with 0 giving PkHash
    on failure with Err:
        produce success with false
    end attempt

    keep PkValid as truth value
    call ct_compare with PkHash and Record.PublicKeyHash and 32 giving PkValid
    if PkValid is false then:
        produce success with false    # public key not trusted
    end if

    # 2. Compute firmware hash
    keep FwHash as bytes
    attempt:
        call Tls.send with 0 and FirmwareData
        call Tls.receive with 0 giving FwHash
    on failure with Err:
        produce success with false
    end attempt

    # 3. Verify hash matches signed value
    keep HashMatch as truth value
    call ct_compare with FwHash and Record.FirmwareHash and 32 giving HashMatch
    produce success with HashMatch
end action
```

---

## Tamper-Evident Audit Log

```
action append_audit_record takes EventCode as u16
                              and ActorID as u32
                              and Data as bytes
                              and DataLen as whole number
                              and LogKey as KeyMaterial
                              and PrevSequence as u32
                              produces AuditRecord:
    use File
    use Timer

    keep Record as AuditRecord
    put EventCode into Record.EventCode
    put ActorID into Record.ActorID
    put the sum of PrevSequence and 1 into Record.Sequence
    call Timer.start with 0 giving Record.Timestamp

    # Hash the data payload
    attempt:
        call Tls.send with 0 and Data
        call Tls.receive with 0 giving Record.DataHash
    on failure with Err:
        produce failure with text "data hash failed"
    end attempt

    # HMAC the full record for tamper detection
    attempt:
        call hmac_sha256 with Data and DataLen and LogKey giving Record.HmacTag
    on failure with Err:
        produce failure with text "audit HMAC failed"
    end attempt

    attempt:
        call File.write with "audit.bin" and EventCode
    on failure with Err:
        produce failure with text "audit log write failed"
    end attempt

    produce success with Record
end action
```

---

## Stdlib Modules for Security

| Module | Use case |
|---|---|
| `Tls` | AES-GCM, TLS handshake, ECDH key exchange, hash primitives |
| `Device` | Hardware TRNG, HSM device node, TrustZone SMC interface |
| `Math` | Big integer helpers, modular arithmetic |
| `Mutex` | Protect key material during multi-threaded operations |
| `MemoryMap` | Map secure memory regions for key storage |
| `File` | Audit log persistence, key file storage |
| `Timer` | Timestamp for audit records, session expiry |

---

## Compile Commands

```bash
# Validate (always first — security code must have zero validator errors)
python dictumc_cli.py secure.dict --validate

# Bare-metal security firmware
python dictumc_cli.py secure.dict --backend c --compile -o secure_fw

# TrustZone C++ TEE application
python dictumc_cli.py trustzone_app.dict --backend cpp --cpp-standard 17 --compile -o ta.elf
```

---

## Domain Rules

1. **Constant-time for all comparisons** involving secret data — use `ct_compare`, never `is equal to` on key bytes.
2. **Zeroize before release** — call `zeroize_key` on every key before it goes out of scope.
3. **No early exit in crypto paths** — all branches must complete the same number of operations.
4. **Fail closed** — on any verification failure, return `false` not an error code that leaks information.
5. **TRNG validation** — verify TRNG output is not all-zeros or all-ones before using as key material.
6. **Key use counting** — enforce `MaxUseCount` on every key; zeroize on expiry.
7. **Audit every security event** — key generation, key use, verification failure, secure boot result.
8. **Never log secret material** — audit records contain hashes and codes, never raw key bytes.
9. **Cache flush after key use** — on platforms where cache flush is required, add the ioctl after key operations.
10. **Session keys expire** — always set `ExpiryTime` on `SecureChannel`; reject use after expiry.
