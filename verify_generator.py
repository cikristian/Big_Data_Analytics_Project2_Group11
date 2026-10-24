"""Section 9.2 - confirm the supplied generator is unchanged (SHA-256 of the handout copy)."""
import hashlib

EXPECTED = "2ea0e59d2b7b987d84a3d151bd9d1ad7b3052bfbc25abf1466c8e94467e9455a"
digest = hashlib.sha256(open("mobile_money_generator.py", "rb").read()).hexdigest()
print("SHA-256:", digest)
print("Generator unchanged:", digest == EXPECTED)
